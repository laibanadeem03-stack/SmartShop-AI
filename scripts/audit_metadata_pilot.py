"""Local-only audit and row-group locality estimate using acquired ID caches."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import json
from pathlib import Path
import time

import metadata_coverage_pilot as pilot


def audit(directory):
    started = time.perf_counter()
    directory = pilot.prep.require_local(directory)
    results = json.loads((directory/'results.json').read_text(encoding='utf-8'))
    if results['status'] != 'complete' or not results['network']['measurement_complete']:
        raise ValueError('Only a completed, metered pilot can be audited')
    if sum(r['payload_bytes'] for r in results['network']['ledger']) != results['network']['response_payload_bytes']:
        raise ValueError('Network ledger total mismatch')
    if results['network']['response_payload_bytes'] > 100*pilot.MIB:
        raise ValueError('Network budget exceeded')
    reference = json.loads((directory/'reference.json').read_text(encoding='utf-8'))
    targets = set(reference['weights'])
    db = pilot.projected_database()
    matched = set()
    audit_shards = []
    # These are compressed-byte estimates from existing footers, not data reads.
    fields = {'title', 'description', 'categories', 'features', 'details'}
    try:
        for shard in results['shards']:
            path = directory/'partial-cache'/(shard['name']+'.parent_asin.partial.parquet')
            metadata = db.execute('''SELECT row_group_id,row_group_num_rows,path_in_schema,total_compressed_size
                                      FROM parquet_metadata(?)''',[str(path)]).fetchall()
            groups = sorted({(g,n) for g,n,_,_ in metadata})
            ends = []
            for _, n in groups:
                ends.append(n+(ends[-1] if ends else 0))
            touched = set()
            index = 0
            for batch in pilot.decoded_batches(db,path):
                for (value,) in batch:
                    if value in targets:
                        matched.add(value)
                        touched.add(groups[bisect_right(ends,index)][0])
                    index += 1
            if index != shard['rows']:
                raise ValueError('Audit row count mismatch')
            all_bytes = Counter()
            touched_bytes = Counter()
            for group, _, column, size in metadata:
                root = column.split(',')[0].strip()
                if root in fields:
                    all_bytes[root] += size
                    if group in touched:
                        touched_bytes[root] += size
            audit_shards.append({'name':shard['name'], 'row_groups':len(groups),
                                 'row_groups_with_selected_ids':len(touched),
                                 'text_column_compressed_bytes_all_groups':dict(all_bytes),
                                 'text_column_compressed_bytes_touched_groups':dict(touched_bytes)})
    finally:
        db.close()
    if len(matched) != results['coverage']['overall']['matched']:
        raise ValueError('Independent projected-ID coverage mismatch')
    all_groups = sum(s['row_groups'] for s in audit_shards)
    touched_groups = sum(s['row_groups_with_selected_ids'] for s in audit_shards)
    all_bytes = sum(sum(s['text_column_compressed_bytes_all_groups'].values()) for s in audit_shards)
    touched_bytes = sum(sum(s['text_column_compressed_bytes_touched_groups'].values()) for s in audit_shards)
    receipt = {'status':'passed', 'matched_products_independently_verified':len(matched),
               'ledger_total_verified':True, 'additional_network_payload_bytes':0,
               'row_groups':all_groups, 'row_groups_with_selected_ids':touched_groups,
               'row_group_touch_percent':100*touched_groups/all_groups,
               'proposed_text_columns':sorted(fields),
               'text_column_compressed_bytes_all_groups':all_bytes,
               'text_column_compressed_bytes_touched_groups':touched_bytes,
               'text_byte_touch_percent':100*touched_bytes/all_bytes,
               'estimates_exclude_headers_redirects_and_retries':True,
               'shards':audit_shards, 'elapsed_seconds':time.perf_counter()-started}
    pilot.prep.write_json(directory/'local_audit.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='shards'},indent=2))
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory',type=Path)
    audit(parser.parse_args().run_directory)
