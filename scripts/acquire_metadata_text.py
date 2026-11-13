"""Acquire four approved metadata columns with a cumulative, metered cap.

Local preparation and final verification run separately from remote acquisition;
existing private artifacts never need new ACLs. No model fitting is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import shutil
import sqlite3
import statistics
import struct
import time
import uuid

import metadata_coverage_pilot as pilot
from bounded_http import BoundedHTTP, TransferStopped

REVISION = pilot.REVISION
FIELDS = ('parent_asin', 'title', 'main_category', 'categories')
NEW_FIELDS = set(FIELDS)-{'parent_asin'}
CAP = 150*pilot.MIB


def column_plan(db, path):
    """Inspect existing local footers; include no gap or unapproved column."""
    size = path.stat().st_size
    with path.open('rb') as stream:
        stream.seek(size-8)
        trailer = stream.read(8)
    if trailer[4:] != b'PAR1':
        raise ValueError('Invalid cached Parquet trailer')
    footer_start = size-8-struct.unpack('<I',trailer[:4])[0]
    rows = db.execute('''SELECT path_in_schema,dictionary_page_offset,
                               data_page_offset,total_compressed_size
                        FROM parquet_metadata(?)''',[str(path)]).fetchall()
    ranges = []
    sizes = Counter()
    observed = set()
    for column, dictionary, data, compressed in rows:
        root = column.split(',')[0].strip()
        if root not in FIELDS:
            continue
        observed.add(root)
        start = min(x for x in (dictionary,data) if x is not None and x >= 4)
        end = start+compressed-1
        if compressed <= 0 or end >= footer_start:
            raise ValueError('Invalid approved-column chunk')
        if root in NEW_FIELDS:
            sizes[root] += compressed
            ranges.append((start,end))
    if observed != set(FIELDS):
        raise ValueError('Approved metadata schema is incomplete')
    merged = []
    for a,b in sorted(ranges):
        if merged and a <= merged[-1][1]:
            raise ValueError('Approved chunks unexpectedly overlap')
        if merged and a == merged[-1][1]+1:
            merged[-1] = (merged[-1][0],b)
        else:
            merged.append((a,b))
    ids,_ = pilot.id_ranges(db,path,footer_start)
    return {'new_ranges':merged, 'column_bytes':dict(sizes),
            'local_copy_ranges':[(0,3),*ids,(footer_start,size-1)]}


def copy_spans(source, destination, spans):
    """Copy cached IDs/container bytes only; never copy the full logical shard."""
    pilot.sparse_file(destination,source.stat().st_size)
    with source.open('rb') as stream, destination.open('r+b') as output:
        for a,b in spans:
            stream.seek(a)
            output.seek(a)
            remaining = b-a+1
            while remaining:
                data = stream.read(min(64*1024,remaining))
                if not data:
                    raise ValueError('Cached source span is truncated')
                output.write(data)
                remaining -= len(data)


def prepare(pilot_directory):
    started = time.perf_counter()
    source = pilot.prep.require_local(pilot_directory)
    result = json.loads((source/'results.json').read_text(encoding='utf-8'))
    receipt = json.loads((source/'post_run_integrity.json').read_text(encoding='utf-8'))
    reference = json.loads((source/'reference.json').read_text(encoding='utf-8'))
    if (result['status']!='complete' or result['revision']!=REVISION
            or not result['network']['measurement_complete']
            or not receipt['protected_sources_unchanged']
            or not receipt['reference_recomputed_and_verified']
            or pilot.prep.sha256(source/'reference.json')!=receipt['reference_sha256']
            or pilot.identifier_hash(reference['weights'])!=pilot.EXPECTED_ID_HASH):
        raise ValueError('Verified pilot provenance/reference requirements failed')
    before = receipt['sources_after']
    # Include all existing subset/evaluation/popularity/CF outputs, plus the
    # immutable ID pilot and cached files, without loading user-ID mappings.
    parents = {Path(p).parent for p in before}
    paths = {p for parent in parents for p in parent.rglob('*') if p.is_file()}
    paths.update(p for p in source.rglob('*') if p.is_file())
    current = pilot.protected_snapshot(sorted(paths))
    if any(current.get(p)!=fingerprint for p,fingerprint in before.items()):
        raise ValueError('A protected artifact differs from the previous verified pilot')
    directory = pilot.prep.LOCAL/('metadata-text-'+uuid.uuid4().hex[:12])
    directory.mkdir(exist_ok=False)
    cache = directory/'partial-cache'
    cache.mkdir()
    disk = shutil.disk_usage(directory)
    pilot.check_cache_space(result['shards'],disk.free)
    db = pilot.projected_database()
    shards = []
    try:
        for shard in result['shards']:
            filename = shard['name']+'.parent_asin.partial.parquet'
            cached = source/'partial-cache'/filename
            planned = column_plan(db,cached)
            destination = cache/(shard['name']+'.approved-columns.partial.parquet')
            copy_spans(cached,destination,planned['local_copy_ranges'])
            shards.append({'name':shard['name'], 'path':shard['path'],
                           'bytes':shard['bytes'], 'lfs_sha256':shard['lfs_sha256'],
                           'cache_name':destination.name,
                           'ranges':planned['new_ranges'], 'column_bytes':planned['column_bytes']})
    finally:
        db.close()
    planned_bytes = sum(b-a+1 for s in shards for a,b in s['ranges'])
    previous_bytes = result['network']['response_payload_bytes']
    if previous_bytes+planned_bytes > CAP:
        raise TransferStopped('Prior ID pilot plus planned text would exceed 150 MiB')
    pilot.prep.write_json(directory/'reference.json',reference)
    pilot.prep.write_json(directory/'input_audit.json',{'sources_before':current})
    plan = {'algorithm_version':'1.0','repository':pilot.REPOSITORY,'revision':REVISION,
            'fields':list(FIELDS),'pilot_directory':str(source),
            'reference_sha256':pilot.prep.sha256(directory/'reference.json'),
            'cumulative_cap_bytes':CAP,'prior_pilot_payload_bytes':previous_bytes,
            'new_stage_payload_ceiling_bytes':CAP-previous_bytes,
            'planned_new_column_bytes':planned_bytes,'shards':shards,
            'disk_free_before_bytes':disk.free,'preparation_seconds':time.perf_counter()-started}
    pilot.prep.write_json(directory/'plan.json',plan)
    print(json.dumps({'prepared_directory':str(directory),'planned_column_bytes':planned_bytes,
                      'planned_new_MiB':planned_bytes/pilot.MIB,
                      'prior_plus_planned_MiB':(previous_bytes+planned_bytes)/pilot.MIB,
                      'preparation_seconds':plan['preparation_seconds']},indent=2))
    return directory


def create_store(path):
    path.touch(exist_ok=False)
    store = sqlite3.connect(path)
    store.execute('PRAGMA cache_size=-8192')
    store.execute('CREATE TABLE records(parent_asin TEXT COLLATE BINARY NOT NULL,title TEXT,main_category TEXT,categories_json TEXT)')
    return store


def store_selected(store, batches, targets):
    count = 0
    for batch in batches:
        values = []
        for identifier,title,main_category,categories in batch:
            if identifier not in targets:
                continue
            if any(v is not None and not isinstance(v,str) for v in (title,main_category)):
                raise ValueError('Unexpected scalar metadata type')
            if categories is not None and (not isinstance(categories,list)
                                          or any(x is not None and not isinstance(x,str) for x in categories)):
                raise ValueError('Unexpected category hierarchy type')
            values.append((identifier,title,main_category,json.dumps(categories,ensure_ascii=False)))
        with store:
            store.executemany('INSERT INTO records VALUES (?,?,?,?)',values)
        count += len(values)
    return count


def normalized_text(value):
    """Quality diagnostic only. Original values are never rewritten."""
    if value is None:
        return ''
    text = re.sub(r'<[^>]*>',' ',html.unescape(value)).strip()
    if text.lower() in ('null','none','nan','n/a','na'):
        return ''
    return text if re.search(r'\w',text,flags=re.UNICODE) else ''


def summarize(store, reference, complete):
    weights = reference['weights']
    training = set(reference['training'])
    counts = Counter()
    ids = Counter()
    useful_ids = set()
    useful_title_ids = set()
    lengths, tokens = [],[]
    normalized_titles = Counter()
    for identifier,title,main_category,categories_json in store.execute('SELECT * FROM records'):
        ids[identifier] += 1
        counts['records'] += 1
        categories = json.loads(categories_json)
        title_text = normalized_text(title)
        main_text = normalized_text(main_category)
        category_texts = [normalized_text(x) for x in categories or []]
        has_categories = any(category_texts)
        counts['null_titles'] += title is None
        counts['blank_titles'] += title is not None and not title.strip()
        counts['missing_or_empty_titles'] += not bool(title_text)
        counts['missing_category_hierarchy'] += not has_categories
        counts['missing_main_category'] += not bool(main_text)
        counts['missing_all_categories'] += not has_categories and not main_text
        counts['usable_title_records'] += bool(title_text)
        counts['usable_title_and_category_records'] += bool(title_text) and (has_categories or bool(main_text))
        counts['usable_text_records'] += bool(title_text) or has_categories or bool(main_text)
        counts['category_only_records'] += not title_text and (has_categories or bool(main_text))
        if title_text or has_categories or main_text:
            useful_ids.add(identifier)
        if title_text:
            useful_title_ids.add(identifier)
            lengths.append(len(title_text))
            words = len(re.findall(r'\w+',title_text))
            tokens.append(words)
            counts['titles_under_three_tokens'] += words<3
            normalized_titles[title_text] += 1
    if not set(ids)<=weights.keys():
        raise ValueError('Export contains an identifier outside the selected reference')
    def segment(values):
        n = len(values & ids.keys())
        return {'matched':n,'total':len(values),'percent':100*n/len(values) if values else None,
                'unmatched' if complete else 'unresolved':len(values)-n}
    return {'complete_scan':complete,'counts':dict(counts),'unique_products':len(ids),
            'id_coverage':segment(set(weights)), 'training_catalog_coverage':segment(training),
            'outside_training_coverage':segment(set(weights)-training),
            'interaction_weighted_coverage_percent':100*sum(weights[x] for x in ids)/sum(weights.values()),
            'duplicate_ids':sum(n>1 for n in ids.values()),'duplicate_excess_records':sum(n-1 for n in ids.values()),
            'products_with_usable_text':len(useful_ids),'products_with_usable_titles':len(useful_title_ids),
            'unique_normalized_titles':len(normalized_titles),
            'repeated_normalized_title_values':sum(n>1 for n in normalized_titles.values()),
            'title_character_min':min(lengths,default=None),
            'title_character_median':statistics.median(lengths) if lengths else None,
            'title_character_max':max(lengths,default=None),
            'title_token_median':statistics.median(tokens) if tokens else None}


def export_jsonl(store,path):
    with path.open('x',encoding='utf-8',newline='\n') as output:
        for identifier,title,main_category,categories_json in store.execute('SELECT * FROM records ORDER BY parent_asin,rowid'):
            record = dict(zip(FIELDS,(identifier,title,main_category,json.loads(categories_json))))
            output.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n')


def retryable_transport(http):
    if not http.ledger:
        return False
    record = http.ledger[-1]
    return (http.measurement_complete and record.get('transport_error',False)
            and 'status' not in record and record['payload_bytes']==0)


def fetch_range(http,url,a,b,size):
    """At most one fresh-connection retry, only before a response body exists."""
    try:
        return http.request(url,byte_range=(a,b),object_size=size)
    except TransferStopped:
        if not retryable_transport(http):
            raise
        http.close()
        http.bounded_transport_retries = getattr(http,'bounded_transport_retries',0)+1
        return http.request(url,byte_range=(a,b),object_size=size)


def completed_range_prefix(ledger,shards):
    expected = [(s['name'],a,b) for s in shards for a,b in s['ranges']]
    completed = 0
    for record in ledger:
        if record.get('status')==206:
            if completed>=len(expected):
                raise ValueError('Too many completed ranges')
            _,a,b = expected[completed]
            if record.get('range')!=[a,b] or record['payload_bytes']!=b-a+1:
                raise ValueError('Ledger is not an exact prefix of the range plan')
            completed += 1
        elif record.get('status') not in (301,302,303,307,308) and not record.get('transport_error'):
            raise ValueError('Unexpected response prevents safe recovery')
    return completed


def recover(directory):
    """One explicit recovery; preserve the initial result and spent-byte ledger."""
    started = time.perf_counter()
    directory = pilot.prep.require_local(directory)
    old = json.loads((directory/'results.json').read_text(encoding='utf-8'))
    plan = json.loads((directory/'plan.json').read_text(encoding='utf-8'))
    network = old['network']
    last = network['ledger'][-1]
    if (old['status']!='stopped' or old.get('stop_reason')!='HTTPS transport failed; no automatic retry'
            or not network['measurement_complete'] or not last.get('transport_error')
            or 'status' in last or last['payload_bytes']!=0
            or sum(r['payload_bytes'] for r in network['ledger'])!=network['response_payload_bytes']
            or old['cumulative_payload_bytes']!=plan['prior_pilot_payload_bytes']+network['response_payload_bytes']
            or old['cumulative_payload_bytes']>CAP
            or plan['revision']!=REVISION or plan['fields']!=list(FIELDS)
            or pilot.prep.sha256(directory/'reference.json')!=plan['reference_sha256']):
        raise ValueError('Safe, measured pre-body transport recovery requirements failed')
    skip = completed_range_prefix(network['ledger'],plan['shards'])
    remaining = sum(b-a+1 for s in plan['shards'] for a,b in s['ranges'])
    remaining -= sum(r['payload_bytes'] for r in network['ledger'] if r.get('status')==206)
    allowance = CAP-old['cumulative_payload_bytes']
    if remaining>allowance:
        raise TransferStopped('Remaining ranges exceed the cumulative allowance')
    with (directory/'recovery_started.json').open('x',encoding='utf-8') as output:
        json.dump({'single_recovery':True,'spent_before_recovery_bytes':old['cumulative_payload_bytes'],
                   'started_utc':datetime.now(timezone.utc).isoformat()},output)
    reference = json.loads((directory/'reference.json').read_text(encoding='utf-8'))
    http = BoundedHTTP(allowance,maximum_limit=CAP,keep_alive=True)
    db = pilot.projected_database()
    db.execute('SET temp_directory=?',[str(directory/'duckdb-temp')])
    db.execute('CREATE TEMP TABLE targets(parent_asin VARCHAR PRIMARY KEY)')
    db.executemany('INSERT INTO targets VALUES (?)',[(x,) for x in reference['weights']])
    store = sqlite3.connect(directory/'selected_metadata.sqlite3')
    store.execute('PRAGMA cache_size=-8192')
    result = {'status':'stopped','revision':REVISION,'fields':list(FIELDS),
              'prior_pilot_payload_bytes':plan['prior_pilot_payload_bytes'],
              'cumulative_cap_bytes':CAP,'shards':list(old['shards']),
              'explicit_recovery_attempts':1,'previous_active_seconds':old['elapsed_seconds']}
    completed_names = {s['name'] for s in old['shards']}
    index = 0
    complete = False
    try:
        http.admit(remaining)
        for shard in plan['shards']:
            cache = directory/'partial-cache'/shard['cache_name']
            if [list(r) for r in column_plan(db,cache)['new_ranges']]!=shard['ranges']:
                raise ValueError('Recovery range whitelist mismatch')
            url = f"{pilot.HF}/datasets/{pilot.REPOSITORY}/resolve/{REVISION}/{shard['path']}"
            for number,(a,b) in enumerate(shard['ranges'],1):
                index += 1
                if index<=skip:
                    continue
                data,_,url = fetch_range(http,url,a,b,shard['bytes'])
                pilot.put_range(cache,a,data)
                if number%100==0:
                    print(f"{shard['name']}: {number}/{len(shard['ranges'])} ranges; cumulative payload {(old['cumulative_payload_bytes']+http.used)/pilot.MIB:.2f} MiB",flush=True)
            if shard['name'] not in completed_names:
                cursor = db.execute('''SELECT p.parent_asin,p.title,p.main_category,p.categories
                                       FROM read_parquet(?) p JOIN targets t USING(parent_asin)''',[str(cache)])
                def batches():
                    while rows:=cursor.fetchmany(4096):
                        yield rows
                matched = store_selected(store,batches(),reference['weights'])
                result['shards'].append({'name':shard['name'],'matched_records':matched})
                print(f"Decoded {shard['name']}: {matched:,} selected records",flush=True)
            # Bound connection lifetime; retain the same meter and ledger.
            http.close()
        complete = True
        result['status']='complete'
    except (TransferStopped,ValueError,OSError,pilot.duckdb.Error) as error:
        result['error_type']=type(error).__name__
        result['stop_reason']=str(error) if isinstance(error,TransferStopped) else 'Local recovery validation/storage failure'
        print('Recovery stopped: '+result['stop_reason'],flush=True)
    finally:
        http.close()
        result['coverage']=summarize(store,reference,complete)
        if complete:
            export_jsonl(store,directory/'selected_metadata.jsonl')
            result['metadata_jsonl_sha256']=pilot.prep.sha256(directory/'selected_metadata.jsonl')
        store.close()
        db.close()
        merged_ledger=network['ledger']+http.ledger
        result['network']={**http.summary(),'ledger':merged_ledger,
                           'budget_bytes':CAP-plan['prior_pilot_payload_bytes'],
                           'response_payload_bytes':network['response_payload_bytes']+http.used,
                           'remaining_bytes':allowance-http.used,'request_attempts':len(merged_ledger),
                           'measurement_complete':network['measurement_complete'] and http.measurement_complete,
                           'bounded_transport_retries':network.get('bounded_transport_retries',0)+getattr(http,'bounded_transport_retries',0)}
        result['cumulative_payload_bytes']=old['cumulative_payload_bytes']+http.used
        result['recovery_seconds']=time.perf_counter()-started
        result['elapsed_seconds']=old['elapsed_seconds']+result['recovery_seconds']
        result['recovery_memory']=pilot.prep.load_local('inspect_ratings').process_memory()
        result['memory']={'peak_working_set_bytes':max(old['memory']['peak_working_set_bytes'],
                                                       result['recovery_memory']['peak_working_set_bytes'])}
        files=[p for p in directory.rglob('*') if p.is_file()]
        result['disk']={'logical_bytes':sum(p.stat().st_size for p in files),
                        'allocated_bytes':sum(pilot.allocated_bytes(p) for p in files)}
        pilot.prep.write_json(directory/'results_recovery.json',result)
        print(json.dumps({k:result[k] for k in ('status','coverage','cumulative_payload_bytes','elapsed_seconds','memory')},indent=2))
    return result


def acquire(directory):
    started = time.perf_counter()
    directory = pilot.prep.require_local(directory)
    plan = json.loads((directory/'plan.json').read_text(encoding='utf-8'))
    if (plan['revision']!=REVISION or plan['fields']!=list(FIELDS)
            or plan['cumulative_cap_bytes']!=CAP
            or plan['new_stage_payload_ceiling_bytes']!=CAP-plan['prior_pilot_payload_bytes']
            or pilot.prep.sha256(directory/'reference.json')!=plan['reference_sha256']):
        raise ValueError('Prepared acquisition manifest validation failed')
    reference = json.loads((directory/'reference.json').read_text(encoding='utf-8'))
    if pilot.identifier_hash(reference['weights'])!=pilot.EXPECTED_ID_HASH:
        raise ValueError('Selected reference ID checksum mismatch')
    with (directory/'network_started.json').open('x',encoding='utf-8') as output:
        json.dump({'single_use':True,'started_utc':datetime.now(timezone.utc).isoformat()},output)
    http = BoundedHTTP(plan['new_stage_payload_ceiling_bytes'],maximum_limit=CAP,keep_alive=True)
    db = pilot.projected_database()
    db.execute('SET temp_directory=?',[str(directory/'duckdb-temp')])
    db.execute('CREATE TEMP TABLE targets(parent_asin VARCHAR PRIMARY KEY)')
    db.executemany('INSERT INTO targets VALUES (?)',[(x,) for x in sorted(reference['weights'])])
    store = create_store(directory/'selected_metadata.sqlite3')
    result = {'status':'stopped','revision':REVISION,'fields':list(FIELDS),
              'prior_pilot_payload_bytes':plan['prior_pilot_payload_bytes'],
              'cumulative_cap_bytes':CAP,'shards':[]}
    complete = False
    try:
        http.admit(plan['planned_new_column_bytes'])
        for shard in plan['shards']:
            cache = directory/'partial-cache'/shard['cache_name']
            # Re-derive the whitelist from local footers instead of trusting a
            # hand-edited plan to authorize descriptions or other column pages.
            approved = column_plan(db,cache)
            if [list(r) for r in approved['new_ranges']]!=shard['ranges']:
                raise ValueError('Range plan differs from the approved columns')
            url = f"{pilot.HF}/datasets/{pilot.REPOSITORY}/resolve/{REVISION}/{shard['path']}"
            for number,(a,b) in enumerate(shard['ranges'],1):
                data,_,url = fetch_range(http,url,a,b,shard['bytes'])
                pilot.put_range(cache,a,data)
                if number%100==0:
                    print(f"{shard['name']}: {number}/{len(shard['ranges'])} ranges; new payload {http.used/pilot.MIB:.2f} MiB",flush=True)
            cursor = db.execute('''SELECT p.parent_asin,p.title,p.main_category,p.categories
                                   FROM read_parquet(?) p JOIN targets t USING(parent_asin)''',[str(cache)])
            def batches():
                while rows:=cursor.fetchmany(4096):
                    yield rows
            matched = store_selected(store,batches(),reference['weights'])
            result['shards'].append({'name':shard['name'],'matched_records':matched})
            print(f"Decoded {shard['name']}: {matched:,} selected records",flush=True)
            # Persist accounting at every completed shard; a killed mid-shard
            # process must not resume or reset its budget automatically.
            pilot.prep.write_json(directory/(shard['name']+'.transport.json'),http.summary())
        complete = True
        result['status'] = 'complete'
    except (TransferStopped,ValueError,OSError,pilot.duckdb.Error) as error:
        result['error_type'] = type(error).__name__
        result['stop_reason'] = str(error) if isinstance(error,TransferStopped) else 'Local metadata validation/storage failure; no fallback attempted'
        print('Acquisition stopped: '+result['stop_reason'],flush=True)
    finally:
        http.close()
        result['coverage'] = summarize(store,reference,complete)
        if complete:
            export_jsonl(store,directory/'selected_metadata.jsonl')
            result['metadata_jsonl_sha256'] = pilot.prep.sha256(directory/'selected_metadata.jsonl')
        store.close()
        db.close()
        result['network'] = http.summary()
        result['network']['bounded_transport_retries'] = getattr(http,'bounded_transport_retries',0)
        result['cumulative_payload_bytes'] = plan['prior_pilot_payload_bytes']+http.used
        files = [p for p in directory.rglob('*') if p.is_file()]
        result['disk'] = {'logical_bytes':sum(p.stat().st_size for p in files),
                          'allocated_bytes':sum(pilot.allocated_bytes(p) for p in files)}
        result['elapsed_seconds'] = time.perf_counter()-started
        result['memory'] = pilot.prep.load_local('inspect_ratings').process_memory()
        pilot.prep.write_json(directory/'results.json',result)
        print(json.dumps({k:result[k] for k in ('status','coverage','cumulative_payload_bytes','elapsed_seconds','memory')},indent=2),flush=True)
    return result


def verify(directory):
    started = time.perf_counter()
    directory = pilot.prep.require_local(directory)
    audit = json.loads((directory/'input_audit.json').read_text(encoding='utf-8'))
    unchanged = pilot.protected_snapshot([Path(p) for p in audit['sources_before']])==audit['sources_before']
    plan = json.loads((directory/'plan.json').read_text(encoding='utf-8'))
    reference_ok = pilot.prep.sha256(directory/'reference.json')==plan['reference_sha256']
    result_path=directory/'results_recovery.json'
    if not result_path.exists():
        result_path=directory/'results.json'
    result = json.loads(result_path.read_text(encoding='utf-8'))
    network = result['network']
    ledger_ok = sum(x['payload_bytes'] for x in network['ledger'])==network['response_payload_bytes']
    cap_ok = result['cumulative_payload_bytes']<=CAP
    values_verified = None
    if result['status']=='complete':
        reference = json.loads((directory/'reference.json').read_text(encoding='utf-8'))
        expected = {}
        with (directory/'selected_metadata.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                record = json.loads(line)
                if set(record)!=set(FIELDS) or record['parent_asin'] not in reference['weights']:
                    raise ValueError('Unexpected exported field or identifier')
                identifier = record['parent_asin']
                value = (record['title'],record['main_category'],
                         json.dumps(record['categories'],ensure_ascii=False))
                expected.setdefault(identifier,[]).append(value)
        source_values = {}
        db = pilot.projected_database()
        try:
            db.execute('CREATE TEMP TABLE targets(parent_asin VARCHAR PRIMARY KEY)')
            db.executemany('INSERT INTO targets VALUES (?)',[(x,) for x in reference['weights']])
            for shard in plan['shards']:
                cursor = db.execute('''SELECT p.parent_asin,p.title,p.main_category,p.categories
                                       FROM read_parquet(?) p JOIN targets t USING(parent_asin)''',
                                    [str(directory/'partial-cache'/shard['cache_name'])])
                while rows:=cursor.fetchmany(4096):
                    for identifier,title,main,categories in rows:
                        source_values.setdefault(identifier,[]).append((title,main,json.dumps(categories,ensure_ascii=False)))
        finally:
            db.close()
        with sqlite3.connect((directory/'selected_metadata.sqlite3').as_uri()+'?mode=ro',uri=True) as store:
            stored = {}
            for identifier,title,main,categories in store.execute('SELECT * FROM records'):
                stored.setdefault(identifier,[]).append((title,main,categories))
        # Source row order does not determine identity; repeated records are
        # compared as multisets so conflicting duplicates cannot be hidden.
        bag = lambda mapping: {identifier:Counter(values) for identifier,values in mapping.items()}
        values_verified = bag(source_values)==bag(expected)==bag(stored)
        if pilot.prep.sha256(directory/'selected_metadata.jsonl')!=result['metadata_jsonl_sha256']:
            values_verified = False
    receipt = {'protected_sources_unchanged':unchanged,'protected_files':len(audit['sources_before']),
               'reference_unchanged':reference_ok,'network_ledger_verified':ledger_ok,'cumulative_budget_verified':cap_ok,
               'all_four_source_values_verified_against_sqlite_and_jsonl':values_verified,
               'verification_additional_network_bytes':0,
               'acquisition_result_file':result_path.name,
               'acquisition_result_sha256':pilot.prep.sha256(result_path),
               'elapsed_seconds':time.perf_counter()-started,
               'memory':pilot.prep.load_local('inspect_ratings').process_memory()}
    pilot.prep.write_json(directory/'post_run_integrity.json',receipt)
    print(json.dumps(receipt,indent=2))
    if not all((unchanged,reference_ok,ledger_ok,cap_ok)) or values_verified is False:
        raise ValueError('Post-run integrity validation failed')
    return receipt


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    stage = parser.add_mutually_exclusive_group(required=True)
    stage.add_argument('--prepare',action='store_true')
    stage.add_argument('--acquire',type=Path)
    stage.add_argument('--verify',type=Path)
    stage.add_argument('--recover',type=Path)
    parser.add_argument('--pilot',type=Path,help='Verified ID-only run; required for --prepare')
    args = parser.parse_args()
    if args.prepare:
        if args.pilot is None:
            parser.error('--prepare requires --pilot')
        prepare(args.pilot)
    elif args.acquire:
        acquire(args.acquire)
    elif args.recover:
        recover(args.recover)
    else:
        verify(args.verify)
