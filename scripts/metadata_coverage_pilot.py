"""Bounded ID-only Amazon metadata coverage; never reads remote text columns."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import time
import uuid

import duckdb

import prepare_evaluation as prep
from bounded_http import BoundedHTTP, TransferStopped

REPOSITORY = 'McAuley-Lab/Amazon-Reviews-2023'
REVISION = '2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e'
FOLDER = 'raw_meta_Cell_Phones_and_Accessories'
HF = 'https://huggingface.co'
NAMES = [f'full-{i:05d}-of-00007.parquet' for i in range(7)]
ID_PATTERN = re.compile(r'[A-Z0-9]{10}\Z', re.ASCII)
EXPECTED_ID_HASH = '6de3a1adf44bd63339601e3f065ac46d056c614caa1b01e15451f136f387594f'
MIB = 1024**2


def identifier_hash(ids):
    return hashlib.sha256(''.join(x+'\n' for x in sorted(ids)).encode('utf-8')).hexdigest()


def projected_database():
    db = duckdb.connect(config={'autoinstall_known_extensions': 'false',
                               'autoload_known_extensions': 'false',
                               'memory_limit': '256MB', 'threads': '2'})
    if not db.execute("SELECT loaded FROM duckdb_extensions() WHERE extension_name='parquet'").fetchone()[0]:
        db.close()
        raise RuntimeError('Approved wheel must include the built-in Parquet reader')
    return db


def sparse_file(path, size):
    """Create exclusively; on Windows explicitly mark sparse before truncating."""
    with Path(path).open('xb') as stream:
        if os.name == 'nt':
            import msvcrt
            returned = ctypes.c_ulong()
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            control = kernel.DeviceIoControl
            control.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
            control.restype = ctypes.c_int
            if not control(msvcrt.get_osfhandle(stream.fileno()), 0x900C4,
                           None, 0, None, 0, ctypes.byref(returned), None):
                raise OSError(ctypes.get_last_error(), 'Cannot mark new cache sparse')
        stream.truncate(size)


def put_range(path, offset, data):
    with Path(path).open('r+b') as stream:
        stream.seek(offset)
        stream.write(data)


def allocated_bytes(path):
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        call = kernel.GetCompressedFileSizeW
        call.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        call.restype = ctypes.c_ulong
        high = ctypes.c_ulong()
        ctypes.set_last_error(0)
        low = call(str(path), ctypes.byref(high))
        if low == 0xFFFFFFFF and ctypes.get_last_error():
            raise OSError(ctypes.get_last_error(), 'Cannot measure cache allocation')
        return low + (high.value << 32)
    return Path(path).stat().st_blocks * 512


def id_ranges(db, path, footer_start):
    """Only ranges for the top-level scalar ID column; never coalesce gaps."""
    rows = db.execute('''SELECT row_group_id, row_group_num_rows, num_values,
                              dictionary_page_offset, data_page_offset,
                              total_compressed_size, type
                       FROM parquet_metadata(?) WHERE path_in_schema='parent_asin'
                       ORDER BY row_group_id''', [str(path)]).fetchall()
    if not rows:
        raise ValueError('No parent_asin column')
    ranges = []
    count = 0
    for group, nrows, nvalues, dictionary, data, compressed, physical in rows:
        if physical != 'BYTE_ARRAY' or nrows != nvalues:
            raise ValueError('Unexpected ID column schema or row count')
        offsets = [x for x in (dictionary, data) if x is not None and x >= 4]
        if not offsets or compressed <= 0:
            raise ValueError('Invalid column offsets')
        start = min(offsets)
        end = start + compressed - 1
        if end >= footer_start:
            raise ValueError('Column chunk overlaps footer')
        ranges.append((start, end))
        count += nrows
    ranges.sort()
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            raise ValueError('ID column chunks unexpectedly overlap')
        if merged and start == merged[-1][1]+1:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged, count


def pin_and_list(http, revision=REVISION):
    if not isinstance(revision,str) or not re.fullmatch('[0-9a-f]{40}', revision):
        raise TransferStopped('An explicit immutable repository revision is required')
    _, headers, _ = http.request(f'{HF}/datasets/{REPOSITORY}/resolve/{revision}/README.md', method='HEAD')
    if headers.get('x-repo-commit', '') != revision:
        raise TransferStopped('Remote revision differs from the requested pin')
    body, _, _ = http.request(f'{HF}/api/datasets/{REPOSITORY}/tree/{revision}/{FOLDER}'
                              '?recursive=false&expand=false&limit=100')
    listing = json.loads(body)
    if not isinstance(listing, list) or len(listing) != 7:
        raise TransferStopped('Expected exactly seven shard entries; no pagination fallback')
    shards = []
    for entry in listing:
        name = entry.get('path', '').removeprefix(FOLDER + '/')
        if entry.get('type') != 'file' or name not in NAMES or entry.get('size', 0) <= 12:
            raise TransferStopped('Unexpected shard listing')
        shards.append({'name': name, 'path': entry['path'], 'bytes': entry['size'],
                       'lfs_sha256': entry.get('lfs', {}).get('oid')})
    if sorted(x['name'] for x in shards) != NAMES:
        raise TransferStopped('Duplicate or missing shard')
    return revision, sorted(shards, key=lambda x: x['name'])


def check_cache_space(shards, available):
    # Sparse flags can leave logical extents physically allocated on Windows.
    required = sum(s['bytes'] for s in shards) + 256*MIB
    if available < required:
        raise OSError('Insufficient disk for conservative full cache extents plus ID aggregation')
    return required


def plan_shard(http, db, directory, revision, shard):
    size = shard['bytes']
    url = f"{HF}/datasets/{REPOSITORY}/resolve/{revision}/{shard['path']}"
    trailer, _, final_url = http.request(url, byte_range=(size-8, size-1), object_size=size)
    footer_size = struct.unpack('<I', trailer[:4])[0]
    if trailer[4:] != b'PAR1' or not 0 < footer_size <= min(8*MIB, size-12):
        raise TransferStopped('Invalid or excessive Parquet footer')
    footer_start = size-8-footer_size
    http.admit(footer_size+4)
    header, _, final_url = http.request(final_url, byte_range=(0, 3), object_size=size)
    if header != b'PAR1':
        raise TransferStopped('Invalid Parquet header')
    footer, _, final_url = http.request(final_url, byte_range=(footer_start, size-9), object_size=size)
    cache = directory / (shard['name'] + '.parent_asin.partial.parquet')
    sparse_file(cache, size)
    put_range(cache, 0, header)
    put_range(cache, footer_start, footer+trailer)
    ranges, rows = id_ranges(db, cache, footer_start)
    return {'cache': cache, 'url': final_url, 'ranges': ranges,
            'rows': rows, 'footer_bytes': footer_size+8,
            'id_compressed_bytes': sum(b-a+1 for a, b in ranges)}


def id_store(path):
    Path(path).touch(exist_ok=False)
    db = sqlite3.connect(path)
    db.execute('PRAGMA cache_size=-8192')
    db.execute('PRAGMA temp_store=MEMORY')
    db.execute('CREATE TABLE identifiers(id TEXT PRIMARY KEY COLLATE BINARY, n INTEGER NOT NULL) WITHOUT ROWID')
    return db


def ingest_ids(store, batches):
    stats = {'rows': 0, 'null_ids': 0, 'blank_ids': 0, 'malformed_ids': 0, 'valid_rows': 0}
    for batch in batches:
        counts = Counter()
        for (value,) in batch:
            stats['rows'] += 1
            if value is None:
                stats['null_ids'] += 1
            elif not isinstance(value, str):
                raise ValueError('ID column is not text')
            elif not value.strip():
                stats['blank_ids'] += 1
            elif not ID_PATTERN.fullmatch(value):
                stats['malformed_ids'] += 1
            else:
                counts[value] += 1
                stats['valid_rows'] += 1
        with store:
            store.executemany('INSERT INTO identifiers VALUES (?,?) ON CONFLICT(id) DO UPDATE SET n=n+excluded.n', counts.items())
    return stats


def decoded_batches(db, path):
    cursor = db.execute('SELECT parent_asin FROM read_parquet(?)', [str(path)])
    while batch := cursor.fetchmany(8192):
        yield batch


def coverage(store, weights, training, complete):
    matched = {key for key in weights if store.execute('SELECT 1 FROM identifiers WHERE id=?', (key,)).fetchone()}
    outside = set(weights)-training
    def segment(ids):
        n = len(ids & matched)
        return {'matched': n, 'total': len(ids), 'percent': 100*n/len(ids) if ids else None,
                'unmatched' if complete else 'unresolved': len(ids)-n}
    weighted = sum(n for key, n in weights.items() if key in matched)
    total = sum(weights.values())
    unique, repeated, excess = store.execute('SELECT COUNT(*),COALESCE(SUM(n>1),0),COALESCE(SUM(n-1),0) FROM identifiers').fetchone()
    return {'complete_scan': complete, 'overall': segment(set(weights)),
            'training_catalog': segment(training), 'outside_training_catalog': segment(outside),
            'interaction_weighted': {'matched': weighted, 'total': total, 'percent': 100*weighted/total},
            'metadata_valid_unique_ids': unique, 'metadata_duplicated_valid_ids': repeated,
            'metadata_duplicate_valid_excess_rows': excess,
            'partial_percentages_are_lower_bounds': not complete}


def references(evaluation):
    manifest_path = evaluation/'split_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source = prep.require_local(manifest['source']['path'])
    expected = {source: manifest['source']['sha256'], manifest_path: prep.sha256(manifest_path)}
    for entry in manifest['partitions'].values():
        expected[prep.require_local(entry['path'])] = entry['sha256']
    for path, digest in expected.items():
        if prep.sha256(path) != digest:
            raise ValueError('An approved input checksum differs')
    weights = Counter(row[1] for row in prep.iter_rows(source))
    training = {row[1] for row in prep.iter_rows(evaluation/'train.csv')}
    if (len(weights), len(training), sum(weights.values()), identifier_hash(weights)) != (12635, 11012, 171104, EXPECTED_ID_HASH):
        raise ValueError('Selected product reference does not match approved integrity checks')
    if not all(ID_PATTERN.fullmatch(x) for x in weights):
        raise ValueError('Unexpected selected identifier format')
    database = evaluation/'evaluation.sqlite3'
    expected[database] = prep.sha256(database)
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
        observed = dict(db.execute('SELECT product_id,COUNT(*) FROM interactions GROUP BY product_id'))
        train_check = {row[0] for row in db.execute("SELECT DISTINCT product_id FROM interactions WHERE window='train'")}
    if observed != weights or train_check != training:
        raise ValueError('Read-only evaluation aggregation disagrees with CSV references')
    return weights, training, expected


def protected_snapshot(paths):
    return {str(p): {'sha256': prep.sha256(p), 'bytes': p.stat().st_size,
                     'mtime_ns': p.stat().st_mtime_ns} for p in paths}


def prepare_run(evaluation, cf_directory, revision=REVISION):
    """Local-only reference preparation; inherited ACLs on NEW files only.

    tempfile's private Windows ACLs prevent the approved network identity from
    reading old artifacts. This stage does not change those ACLs or copy users.
    """
    if revision != REVISION:
        raise ValueError('This pipeline requires the approved immutable metadata revision')
    evaluation = prep.require_local(evaluation)
    cf_directory = prep.require_local(cf_directory)
    parent = prep.require_local(prep.LOCAL)
    disk = shutil.disk_usage(parent)
    if disk.free < 768*MIB:
        raise OSError('Need at least 768 MiB free for isolated cache and ID aggregation')
    weights, training, expected = references(evaluation)
    # Record CF files without loading their raw-ID mapping or predictions.
    paths = list(expected) + [p for p in cf_directory.iterdir() if p.is_file()]
    before = protected_snapshot(paths)
    directory = parent/('metadata-pilot-'+uuid.uuid4().hex[:12])
    directory.mkdir(exist_ok=False)
    prep.write_json(directory/'reference.json', {'weights': weights, 'training': sorted(training),
                                               'id_set_sha256': identifier_hash(weights)})
    prep.write_json(directory/'inputs_audit.json', {'sources_before': before, 'revision':revision,
                                                  'reference_sha256': prep.sha256(directory/'reference.json'),
                                                  'disk_free_before_bytes': disk.free})
    print('Prepared ignored product-only reference: '+str(directory), flush=True)
    return directory


def verify_run(directory):
    directory = prep.require_local(directory)
    before = json.loads((directory/'inputs_audit.json').read_text(encoding='utf-8'))['sources_before']
    after = protected_snapshot([Path(p) for p in before])
    evaluation = next(Path(p).parent for p in before if Path(p).name == 'split_manifest.json')
    weights, training, _ = references(evaluation)
    reference = json.loads((directory/'reference.json').read_text(encoding='utf-8'))
    reference_matches = reference['weights'] == weights and set(reference['training']) == training
    receipt = {'protected_sources_unchanged': before == after,
               'reference_recomputed_and_verified': reference_matches,
               'reference_sha256': prep.sha256(directory/'reference.json'),
               'verified_files': len(before), 'sources_after': after}
    prep.write_json(directory/'post_run_integrity.json', receipt)
    print(json.dumps({'protected_sources_unchanged': before == after, 'verified_files': len(before)}))
    if before != after or not reference_matches:
        raise RuntimeError('Protected source fingerprint changed')
    return receipt


def run_prepared(directory):
    started = time.perf_counter()
    directory = prep.require_local(directory)
    reference = json.loads((directory/'reference.json').read_text(encoding='utf-8'))
    weights, training = reference['weights'], set(reference['training'])
    if (identifier_hash(weights) != EXPECTED_ID_HASH
            or len(weights) != 12635 or len(training) != 11012
            or sum(weights.values()) != 171104 or not training <= weights.keys()):
        raise ValueError('Prepared reference integrity mismatch')
    audit = json.loads((directory/'inputs_audit.json').read_text(encoding='utf-8'))
    if audit.get('revision',REVISION) != REVISION:
        raise ValueError('Prepared run uses a different metadata revision')
    if ('reference_sha256' in audit
            and prep.sha256(directory/'reference.json') != audit['reference_sha256']):
        raise ValueError('Prepared product-only reference checksum changed')
    if shutil.disk_usage(directory).free < 768*MIB:
        raise OSError('Insufficient isolated cache disk space')
    cache_directory = directory/'partial-cache'
    cache_directory.mkdir()
    http = BoundedHTTP()
    store = id_store(directory/'metadata_ids.sqlite3')
    db = projected_database()
    db.execute('SET temp_directory=?', [str(directory/'duckdb-temp')])
    result = {'status': 'stopped', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'algorithm_version': '1.0', 'repository': REPOSITORY,
              'requested_column': 'parent_asin', 'reference_id_set_sha256': identifier_hash(weights),
              'duckdb_version': duckdb.__version__, 'extensions_installed': [],
              'disk_free_before_bytes': audit['disk_free_before_bytes'],
              'sources_before': audit['sources_before'], 'shards': [], 'metadata_counts': {}}
    completed = False
    try:
        revision, shards = pin_and_list(http,audit.get('revision',REVISION))
        result['revision'] = revision
        result['shards'] = shards
        result['reserved_disk_budget_bytes'] = check_cache_space(shards, shutil.disk_usage(directory).free)
        plans = []
        for shard in shards:
            plan = plan_shard(http, db, cache_directory, revision, shard)
            plans.append(plan)
            shard.update({k: plan[k] for k in ('rows', 'footer_bytes', 'id_compressed_bytes')})
            shard['id_ranges'] = plan['ranges']
            print(f"Planned {shard['name']}: {plan['rows']:,} rows, {plan['id_compressed_bytes']:,} ID bytes", flush=True)
        planned = sum(p['id_compressed_bytes'] for p in plans)
        result['planned_id_payload_bytes'] = planned
        http.admit(planned)
        totals = Counter()
        for shard, plan in zip(shards, plans):
            for a, b in plan['ranges']:
                body, _, plan['url'] = http.request(plan['url'], byte_range=(a, b), object_size=shard['bytes'])
                put_range(plan['cache'], a, body)
            stats = ingest_ids(store, decoded_batches(db, plan['cache']))
            if stats['rows'] != plan['rows']:
                raise ValueError('Decoded ID count differs from Parquet row groups')
            totals.update(stats)
            result['metadata_counts'] = dict(totals)
            shard['decoded'] = True
            print(f"Decoded {shard['name']}: {stats['rows']:,} ID rows; budget {http.used/MIB:.3f} MiB", flush=True)
        completed = True
        result['status'] = 'complete'
    except (TransferStopped, ValueError, OSError, duckdb.Error) as error:
        # Do not include remote payloads, signed URLs, or IDs in error output.
        result['error_type'] = type(error).__name__
        result['stop_reason'] = (str(error) if isinstance(error, TransferStopped)
                                 else 'Local validation/storage/Parquet failure; no fallback attempted')
        print('Pilot stopped: '+result['stop_reason'], flush=True)
    finally:
        result['coverage'] = coverage(store, weights, training, completed)
        store.close()
        db.close()
        result['protected_sources_unchanged'] = 'pending local --verify-run receipt'
        result['network'] = http.summary()
        files = [p for p in directory.rglob('*') if p.is_file()]
        result['disk'] = {'logical_bytes': sum(p.stat().st_size for p in files),
                          'allocated_bytes': sum(allocated_bytes(p) for p in files),
                          'cache_is_sparse_partial_not_complete_shards': True}
        result['elapsed_seconds'] = time.perf_counter()-started
        result['memory'] = prep.load_local('inspect_ratings').process_memory()
        prep.write_json(directory/'results.json', result)
        print(json.dumps({'run_directory': str(directory), 'status': result['status'],
                          'coverage': result['coverage'], 'network_bytes': http.used,
                          'seconds': result['elapsed_seconds'], 'memory': result['memory']}, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path)
    parser.add_argument('--cf-artifacts', type=Path)
    parser.add_argument('--revision',default=REVISION,choices=[REVISION],help='Approved immutable source revision')
    stage = parser.add_mutually_exclusive_group(required=True)
    stage.add_argument('--prepare-only', action='store_true')
    stage.add_argument('--prepared-run', type=Path)
    stage.add_argument('--verify-run', type=Path)
    args = parser.parse_args()
    if args.prepare_only:
        if args.evaluation is None or args.cf_artifacts is None:
            parser.error('--prepare-only requires --evaluation and --cf-artifacts')
        prepare_run(args.evaluation, args.cf_artifacts,args.revision)
    elif args.verify_run:
        verify_run(args.verify_run)
    else:
        run_prepared(args.prepared_run)
