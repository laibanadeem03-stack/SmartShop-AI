"""Four predeclared TF-IDF configurations on immutable chronological splits."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import tempfile
import time

import joblib
import numpy as np
from scipy import sparse
from threadpoolctl import threadpool_limits

import content_tfidf as content
import evaluate_item_cf as cf_evaluation
import evaluate_popularity as evaluation
import item_cf
import popularity_baseline as popularity
import prepare_evaluation as prep

CONFIGURATIONS = ((2, 0.80), (2, 0.95), (1, 0.80), (1, 0.95))
METADATA_SHA = '12b6cfb3a1e664ff0d2273b6f6aeddc0dda9a94aee7d8bfcc5b02876f56d178b'


def name_for(min_df, title_weight):
    return f'tfidf_df{min_df}_title{round(title_weight*100)}'


def select_configuration(results):
    names = [name_for(df, weight) for df, weight in CONFIGURATIONS]
    if any(results[name]['segments']['overall']['ndcg_at_10'] is None for name in names):
        raise ValueError('Validation requires positive targets')
    return max(names, key=lambda name: results[name]['segments']['overall']['ndcg_at_10'])


def fingerprints(paths):
    return {str(path): {'sha256': prep.sha256(path), 'bytes': path.stat().st_size,
                        'mtime_ns': path.stat().st_mtime_ns} for path in paths}


def metadata_acquisition(directory):
    """A present recovery receipt is authoritative, including failed recovery."""
    path = directory/'results_recovery.json'
    if not path.exists():
        path = directory/'results.json'
    result = json.loads(path.read_text(encoding='utf-8'))
    receipt = json.loads((directory/'post_run_integrity.json').read_text(encoding='utf-8'))
    if (result.get('status') != 'complete'
            or receipt.get('all_four_source_values_verified_against_sqlite_and_jsonl') is not True
            or receipt.get('protected_sources_unchanged') is not True
            or prep.sha256(directory/'selected_metadata.jsonl') != result.get('metadata_jsonl_sha256')):
        raise ValueError('Metadata acquisition is not verified')
    if 'acquisition_result_sha256' in receipt and (
            receipt.get('acquisition_result_file') != path.name
            or receipt['acquisition_result_sha256'] != prep.sha256(path)):
        raise ValueError('Acquisition receipt binding differs')
    return result


def evaluate(rows, ranking, snapshot, seen, begin, end, path, recommender=None):
    value = evaluation.evaluate_window(rows, ranking, snapshot, seen, begin, end,
                                       prediction_path=path, recommender=recommender)
    if recommender is not None:
        value['personalization'] = recommender.usage_summary()
    return value


def run(evaluation_directory, metadata_directory, cf_directory, report_path,
        expected_catalog=11012, expected_metadata=12635):
    started = time.perf_counter()
    source = prep.require_local(evaluation_directory)
    metadata_directory = prep.require_local(metadata_directory)
    cf_directory = prep.require_local(cf_directory)
    report_path = Path(report_path).resolve()
    if report_path.exists() or not report_path.parent.is_dir():
        raise ValueError('Report must be a new file under an existing directory')
    if shutil.disk_usage(prep.LOCAL).free < 500*prep.MIB:
        raise OSError('Need 500 MiB free for content artifacts and predictions')
    manifest_path = source/'split_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    train = cf_evaluation.verify_partition(manifest['partitions']['train'])
    validation_path = cf_evaluation.verify_partition(manifest['partitions']['validation'])
    protocol = manifest['protocol']
    train_end, val_end = protocol['train_end_inclusive_ms'], protocol['validation_end_inclusive_ms']
    metadata_path = metadata_directory/'selected_metadata.jsonl'
    acquisition = metadata_acquisition(metadata_directory)
    expected_sha = acquisition['metadata_jsonl_sha256']
    if expected_metadata == 12635 and expected_sha != METADATA_SHA:
        raise ValueError('Metadata is not the approved acquisition')
    metadata = content.load_metadata(metadata_path, expected_sha)
    if expected_metadata is not None and len(metadata) != expected_metadata:
        raise ValueError('Unexpected selected metadata catalog')
    # Test CSV contents/checksum are deliberately deferred until selection.
    protected_paths = {manifest_path, train, validation_path}
    protected_paths.update(p for p in metadata_directory.rglob('*') if p.is_file())
    protected_paths.update(p for p in cf_directory.rglob('*') if p.is_file())
    protected = fingerprints(sorted(protected_paths))
    subset = prep.require_local(manifest['source']['path'])
    subset_stat = (subset.stat().st_size, subset.stat().st_mtime_ns)
    directory = Path(tempfile.mkdtemp(prefix='content-tfidf-', dir=prep.LOCAL))
    environment = {'python': platform.python_version(), 'executable': __import__('sys').executable,
                   'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
                   'numeric_threads': 1, 'isolated_venv': __import__('sys').prefix != __import__('sys').base_prefix}
    prep.write_json(directory/'environment.json', environment)
    snapshot = popularity.fit_training(prep.iter_rows(train), train_end)
    if snapshot['interaction_count'] != manifest['partitions']['train']['interactions']:
        raise ValueError('Training interaction count differs from existing manifest')
    positive, users, items = item_cf.positive_matrix(prep.iter_rows(train), snapshot)
    if expected_catalog is not None and len(items) != expected_catalog:
        raise ValueError('Unexpected primary training catalog')
    frozen_snapshot = popularity.fingerprint(snapshot)
    prep.write_json(directory/'training_snapshot.json', {'fingerprint': frozen_snapshot,
                                                         'training': popularity.snapshot_payload(snapshot)})
    frozen_positive = item_cf.array_fingerprint(positive, users, items)
    item_cf.save_sparse(directory/'positive_training.npz', positive)
    prep.write_json(directory/'id_mappings.json', {'users': users, 'products': items})
    count_rank = popularity.build_ranking(snapshot)
    prep.write_json(directory/'count_ranking.json', count_rank)
    validation_rows = list(prep.iter_rows(validation_path))
    if len(validation_rows) != manifest['partitions']['validation']['interactions']:
        raise ValueError('Validation interaction count differs from manifest')
    validation = {'count': evaluate(validation_rows, count_rank, snapshot, snapshot['seen'], train_end, val_end,
                                    directory/'validation_predictions_count.csv')}
    matrices, models, statistics, fields_by_df, frozen_fields = {}, {}, {}, {}, {}
    for min_df, weight in CONFIGURATIONS:
        name = name_for(min_df, weight)
        if min_df not in fields_by_df:
            fields = content.fit_fields(metadata, items, min_df)
            fields_by_df[min_df] = fields
            frozen_fields[str(min_df)] = content.field_fingerprint(fields)
            joblib.dump({'title': fields['title_vectorizer'], 'category': fields['category_vectorizer']},
                        directory/f'vectorizers_df{min_df}.joblib', compress=3)
            item_cf.save_sparse(directory/f'title_df{min_df}.npz', fields['title'])
            item_cf.save_sparse(directory/f'category_df{min_df}.npz', fields['category'])
        fields = fields_by_df[min_df]
        if fields['items'] != items:
            raise RuntimeError('Feature rows do not align with the training catalog')
        matrix = content.combine_fields(fields, weight)
        matrices[name] = matrix
        models[name] = item_cf.array_fingerprint(matrix, items=items)
        item_cf.save_sparse(directory/f'features_{name}.npz', matrix)
        statistics[name] = {'min_df': min_df, 'title_weight': weight,
                            'title_features': fields['title'].shape[1], 'category_features': fields['category'].shape[1],
                            'shape': list(matrix.shape), 'nnz': matrix.nnz,
                            'payload_bytes': item_cf.payload_bytes(matrix),
                            'zero_vectors': int(np.count_nonzero(np.diff(matrix.indptr)==0)),
                            'clean_empty_titles': fields['clean_empty_titles'],
                            'clean_empty_categories': fields['clean_empty_categories'],
                            'field_fit_seconds_shared_for_weight_variants': fields['fit_seconds'],
                            'artifact_bytes': (directory/f'features_{name}.npz').stat().st_size,
                            'fingerprint': models[name]}
        recommender = content.ContentRecommender(positive, users, items, matrix, snapshot)
        validation[name] = evaluate(validation_rows, count_rank, snapshot, snapshot['seen'], train_end, val_end,
                                    directory/f'validation_predictions_{name}.csv', recommender)
        print(f"Validation {name}: NDCG@10={validation[name]['segments']['overall']['ndcg_at_10']:.10f}", flush=True)
    if {str(df): content.field_fingerprint(fields) for df,fields in fields_by_df.items()} != frozen_fields:
        raise RuntimeError('Text statistics changed during validation')
    selected = select_configuration(validation)
    selection = {'selected_content': selected, 'criterion': 'validation macro NDCG@10',
                 'tie_priority': [name_for(df,w) for df,w in CONFIGURATIONS],
                 'validation_ndcg': {name: value['segments']['overall']['ndcg_at_10'] for name,value in validation.items()},
                 'test_used_for_selection': False, 'training_fingerprint': frozen_snapshot,
                 'positive_fingerprint': frozen_positive, 'selected_model_fingerprint': models[selected],
                 'field_fingerprints': frozen_fields}
    prep.write_json(directory/'validation_selection.json', selection)
    # All control/test result reads occur after configuration selection.
    prior = json.loads((source/'results.json').read_text(encoding='utf-8'))
    cf_prior = json.loads((cf_directory/'results.json').read_text(encoding='utf-8'))
    cf_evaluation.assert_same_metrics(validation['count'], prior['validation']['count'])
    if frozen_snapshot != prior['training']['fingerprint']:
        raise RuntimeError('Count training statistics changed')
    cf_name = cf_prior['selection']['best_cf_configuration']
    if cf_name != 'item_cf_k50_lambda10':
        raise ValueError('Approved CF control configuration changed')
    cf_mapping = json.loads((cf_directory/'id_mappings.json').read_text(encoding='utf-8'))
    cf_positive = sparse.load_npz(cf_directory/'positive_training.npz')
    cf_graph = sparse.load_npz(cf_directory/f'neighbors_{cf_name}.npz')
    if (cf_mapping != {'users': users, 'products': items}
            or item_cf.array_fingerprint(cf_positive, users, items) != frozen_positive):
        raise RuntimeError('CF and content training mappings/profiles disagree')
    cf_graph_fingerprint = item_cf.array_fingerprint(cf_graph)
    cf_model = item_cf.ItemRecommender(cf_positive, users, items, cf_graph, snapshot)
    validation[cf_name] = evaluate(validation_rows, count_rank, snapshot, snapshot['seen'], train_end, val_end,
                                   directory/f'validation_predictions_{cf_name}.csv', cf_model)
    cf_evaluation.assert_same_metrics(validation[cf_name], cf_prior['validation'][cf_name])
    test_seen = popularity.extend_history(snapshot['seen'], validation_rows, val_end)
    test_path = cf_evaluation.verify_partition(manifest['partitions']['test'])
    test_before = fingerprints([test_path])
    test_rows = list(prep.iter_rows(test_path))
    if len(test_rows) != manifest['partitions']['test']['interactions']:
        raise ValueError('Test interaction count differs from manifest')
    test = {'count': evaluate(test_rows, count_rank, snapshot, test_seen, val_end, None,
                              directory/'test_predictions_count.csv')}
    cf_evaluation.assert_same_metrics(test['count'], prior['test']['count'])
    cf_model = item_cf.ItemRecommender(cf_positive, users, items, cf_graph, snapshot)
    test[cf_name] = evaluate(test_rows, count_rank, snapshot, test_seen, val_end, None,
                             directory/f'test_predictions_{cf_name}.csv', cf_model)
    cf_evaluation.assert_same_metrics(test[cf_name], cf_prior['test'][cf_name])
    model = content.ContentRecommender(positive, users, items, matrices[selected], snapshot)
    test[selected] = evaluate(test_rows, count_rank, snapshot, test_seen, val_end, None,
                              directory/f'test_predictions_{selected}.csv', model)
    if (popularity.fingerprint(snapshot) != frozen_snapshot
            or item_cf.array_fingerprint(positive, users, items) != frozen_positive
            or item_cf.array_fingerprint(cf_graph) != cf_graph_fingerprint
            or any(item_cf.array_fingerprint(matrix, items=items) != models[name] for name,matrix in matrices.items())
            or {str(df): content.field_fingerprint(f) for df,f in fields_by_df.items()} != frozen_fields):
        raise RuntimeError('A frozen training/text model changed during evaluation')
    if fingerprints(sorted(protected_paths)) != protected or fingerprints([test_path]) != test_before:
        raise RuntimeError('An existing artifact or partition changed')
    if (prep.sha256(subset) != manifest['source']['sha256']
            or (subset.stat().st_size, subset.stat().st_mtime_ns) != subset_stat):
        raise RuntimeError('Prepared subset changed')
    prep.write_json(directory/'input_integrity.json', {'protected_sources': protected, 'test': test_before,
                                                      'subset_sha256': manifest['source']['sha256'], 'unchanged': True})
    result = {'status': 'complete', 'algorithm_version': '1.0', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'run_directory': str(directory), 'environment': environment, 'selection': selection,
              'validation': validation, 'test': test, 'models': statistics,
              'metadata_sha256': expected_sha, 'split_manifest_sha256': protected[str(manifest_path)]['sha256'],
              'training': {'interactions': snapshot['interaction_count'], 'users': len(users), 'products': len(items),
                           'positive_interactions': positive.nnz,
                           'users_without_positive_seeds': int(np.count_nonzero(np.diff(positive.indptr)==0))},
              'integrity': {'source_files_unchanged': True, 'protected_files': len(protected_paths)+2,
                            'count_metrics_and_prediction_hashes_unchanged': True,
                            'cf_metrics_and_prediction_hashes_unchanged': True,
                            'test_interactions_read_after_selection': True,
                            'all_text_fit_on_training_catalog_only': True, 'frozen_models_unchanged': True},
              'resources': {'elapsed_seconds': time.perf_counter()-started,
                            **prep.load_local('inspect_ratings').process_memory(),
                            'retained_artifact_bytes_before_results': sum(p.stat().st_size for p in directory.iterdir() if p.is_file())},
              'implementation_sha256': {name: prep.sha256(Path(__file__).with_name(name)) for name in
                                        ('content_tfidf.py','evaluate_content.py','evaluate_popularity.py','item_cf.py','popularity_baseline.py')}}
    prep.write_json(directory/'results.json', result)
    with report_path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(report_markdown(result))
    print(json.dumps({'run_directory': str(directory), 'selected': selected,
                      'test': test[selected]['segments']['overall'], 'resources': result['resources']}, indent=2))
    return result


def report_markdown(result):
    selected = result['selection']['selected_content']
    lines = ['# SmartShop-AI TF-IDF content results', '',
             f'Selected content model: **{selected}**, using validation macro NDCG@10 only.', '',
             '## Validation', '', '| Model | Recall@10 | NDCG@10 | Catalog coverage | Personalized users | Fallback slots |',
             '|---|---:|---:|---:|---:|---:|']
    cf_name = 'item_cf_k50_lambda10'
    for name in ['count', cf_name, *(name_for(df,w) for df,w in CONFIGURATIONS)]:
        value = result['validation'][name]
        m, u = value['segments']['overall'], value.get('personalization', {})
        lines.append(f"| {name} | {m['recall_at_10']:.8f} | {m['ndcg_at_10']:.8f} | {m['catalog_coverage_at_10']:.8f} | {u.get('fraction_users_personalized',0):.2%} | {u.get('fraction_fallback_slots',1):.2%} |")
    lines += ['', '## Frozen test comparison', '',
              '| Model | Recall@10 | NDCG@10 | Catalog coverage | Hits | Personalized users | Fallback slots |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for name in ['count', cf_name, selected]:
        value = result['test'][name]
        m, u = value['segments']['overall'], value.get('personalization', {})
        lines.append(f"| {name} | {m['recall_at_10']:.8f} | {m['ndcg_at_10']:.8f} | {m['catalog_coverage_at_10']:.8f} | {m['hits_at_10']} | {u.get('fraction_users_personalized',0):.2%} | {u.get('fraction_fallback_slots',1):.2%} |")
    lines += ['', '## Selected-model test segments', '', '| Segment | Positive users | Recall@10 | NDCG@10 |', '|---|---:|---:|---:|']
    for name in ['overall','warm_users','cold_users',*evaluation.FOUR_SEGMENTS,'history_0','history_1_2','history_3_4','history_5_plus']:
        m = result['test'][selected]['segments'][name]
        fmt = lambda v: 'undefined' if v is None else f'{v:.8f}'
        lines.append(f"| {name} | {m['evaluated_users']} | {fmt(m['recall_at_10'])} | {fmt(m['ndcg_at_10'])} |")
    r = result['resources']
    lines += ['', '## Models and resources', '', '| Model | Shape | Nonzeros | Zero rows | Array MiB | File MiB |', '|---|---|---:|---:|---:|---:|']
    for name,m in result['models'].items():
        lines.append(f"| {name} | {m['shape']} | {m['nnz']:,} | {m['zero_vectors']} | {m['payload_bytes']/prep.MIB:.3f} | {m['artifact_bytes']/prep.MIB:.3f} |")
    lines += ['', f"Pipeline time: {r['elapsed_seconds']:.3f} seconds. Peak working set: {r['peak_working_set_bytes']/prep.MIB:.2f} MiB. Retained artifacts before result/report writes: {r['retained_artifact_bytes_before_results']/prep.MIB:.2f} MiB.", '',
              f"Ignored run: `{result['run_directory']}`. Metadata SHA-256: `{result['metadata_sha256']}`.", '',
              '## Interpretation and integrity', '',
              'All primary candidates, vocabulary, and IDF use the same 11,012 training-observed products. Ratings 4–5 seed frozen profiles; every rating enters seen masks. Test masks include validation history, but profiles, IDF, and popularity stay frozen. Off-catalog positives remain misses in overall metrics. No negative sampling, full item-item matrix, CF blending, or candidate expansion is used.', '',
              'Count and frozen CF validation/test cohort metrics and prediction hashes reproduce their prior results exactly. Source subset, partitions, metadata, and CF files remain unchanged. Model selection and tie priority were saved before test interactions were read. Personalized-user/fallback rates use all holdout users; ranking metrics and catalog coverage use the existing positive-user cohort.', '',
              'The current metadata snapshot may not reflect titles/categories available at the March 2021 training cutoff. Fitting IDF on training products cannot remove historical-attribute uncertainty. Retrospective five-core selection, generic category overlap, short/marketing text, and repeated titles remain limitations. Cold products stay unreachable under this frozen training-catalog protocol. Offline differences are point estimates, not significance or online-benefit claims.', '',
              'The approved CF baseline remains unchanged; choosing the best content configuration does not automatically replace the project default. See `docs/content_strategy.md` for configuration, tests, environment, and reproduction commands. Stop for review before hybrid or application work.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--cf', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True, help='New output filename')
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        run(args.evaluation, args.metadata, args.cf, args.report)
