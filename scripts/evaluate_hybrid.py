"""Validate four frozen-model RRF weights; lock strict default gate before test."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import shutil
import statistics
import tempfile
import time

from threadpoolctl import threadpool_limits

import evaluate_content as content_evaluation
import content_tfidf as content
import evaluate_item_cf as cf_evaluation
import evaluate_popularity as evaluation
import hybrid_ranker as hybrid
import item_cf
import popularity_baseline as popularity
import prepare_evaluation as prep


def decide_default(validation, content_name):
    names = [hybrid.name_for(weight) for weight in hybrid.CF_WEIGHTS]
    scores = {name:validation[name]['segments']['overall']['ndcg_at_10'] for name in [content_name,*names]}
    if any(value is None or not math.isfinite(value) for value in scores.values()):
        raise ValueError('Validation must contain positive targets')
    selected = max(names,key=lambda name:scores[name])
    improves = scores[selected] > scores[content_name]
    return {'selected_hybrid':selected,'selected_cf_weight':hybrid.CF_WEIGHTS[names.index(selected)],
            'default_model':'hybrid' if improves else 'content','strict_validation_improvement':improves,
            'content_validation_ndcg':scores[content_name],'best_hybrid_validation_ndcg':scores[selected],
            'validation_ndcg':scores,'tie_priority':names,'test_used_for_selection':False}


class CachedPredictions:
    def __init__(self,predictions,masks):
        self.predictions,self.masks = predictions,masks
        self.last_sources = []

    def __call__(self,user,seen,k=10):
        if k!=10 or frozenset(seen)!=self.masks[user]:
            raise ValueError('Cached predictions belong to a different exclusion window')
        result,sources = self.predictions[user]
        self.last_sources = sources
        return result


def evaluate_grid(rows,cf,cb,begin,end,directory):
    """One component-score pass; cache only four top-10 lists per user."""
    started = time.perf_counter()
    users = sorted({row[0] for row in rows})
    models = {hybrid.name_for(w):hybrid.HybridRecommender(cf,cb,w) for w in hybrid.CF_WEIGHTS}
    cache = {name:{} for name in models}
    query_ns = {name:[] for name in models}
    masks = {}
    first = next(iter(models.values()))
    for number,user in enumerate(users,1):
        seen = cb.snapshot['seen'].get(user,set())
        masks[user] = frozenset(seen)
        tick = time.perf_counter_ns()
        signals = first.prepare(user,seen)
        preparation_ns = time.perf_counter_ns()-tick
        for name,model in models.items():
            tick = time.perf_counter_ns()
            result = model.recommend_prepared(signals,seen)
            query_ns[name].append(preparation_ns+time.perf_counter_ns()-tick)
            cache[name][user] = (result,list(model.last_sources))
        if number%2000==0:
            print(f'Validation fusion: {number:,}/{len(users):,} users',flush=True)
    generation_seconds = time.perf_counter()-started
    output = {}
    ranking = popularity.build_ranking(cb.snapshot)
    for name,model in models.items():
        callback = CachedPredictions(cache[name],masks)
        value = evaluation.evaluate_window(rows,ranking,cb.snapshot,cb.snapshot['seen'],begin,end,
                    prediction_path=directory/f'validation_predictions_{name}.csv',recommender=callback)
        value['personalization'] = model.usage_summary()
        r = value['resources']
        r['cached_metric_evaluation_seconds'] = r.pop('elapsed_seconds')
        r['cached_prediction_lookup_median_microseconds'] = r.pop('recommendation_latency_median_microseconds')
        r['cached_prediction_lookup_p95_microseconds'] = r.pop('recommendation_latency_p95_microseconds')
        times = sorted(query_ns[name])
        r['recommendation_latency_median_microseconds'] = statistics.median(times)/1000
        r['recommendation_latency_p95_microseconds'] = times[math.ceil(.95*len(times))-1]/1000
        r['latency_scope'] = 'measured component preparation plus variant fusion; shared preparation counted per variant'
        output[name] = value
        print(f"Validation {name}: NDCG@10={value['segments']['overall']['ndcg_at_10']:.10f}",flush=True)
    return output,{'component_generation_and_fusion_seconds':generation_seconds,
                   'users':len(users),'cached_top_k':10,'cached_variants':len(models),
                   'cached_recommendations':sum(len(items[0]) for values in cache.values() for items in values.values()),
                   'full_user_catalog_scores_cached':False}


def frozen_fingerprint(cf,cb):
    return {'training':popularity.fingerprint(cb.snapshot),
            'positive':item_cf.array_fingerprint(cb.positive,cb.users,cb.items),
            'content':item_cf.array_fingerprint(cb.features,items=cb.items),
            'cf_graph':item_cf.array_fingerprint(cf.graph)}


class EvidenceWriter:
    def __init__(self,model,output,rich_output,rich_user_limit=128):
        self.model,self.output,self.rich_output = model,output,rich_output
        self.rich_user_limit = rich_user_limit
        self.users = 0
        self.last_sources = []
        self.rows = self.rich_rows = 0

    def __call__(self,user,seen,k=10):
        result = self.model(user,seen,k)
        self.last_sources = self.model.last_sources
        self.users += 1
        for rank,trace in enumerate(self.model.last_evidence,1):
            row = {'user_id':user,'rank':rank,**trace}
            self.output.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
            self.rows += 1
            if self.users<=self.rich_user_limit:
                detail = {'user_id':user,'rank':rank,**self.model.explain(user,trace)}
                self.rich_output.write(json.dumps(detail,ensure_ascii=False,allow_nan=False)+'\n')
                self.rich_rows += 1
        return result


def run(evaluation_directory,content_directory,cf_directory,report_path,
        expected_catalog=11012,expected_content='tfidf_df2_title80'):
    started = time.perf_counter()
    source = prep.require_local(evaluation_directory)
    cb_dir,cf_dir = prep.require_local(content_directory),prep.require_local(cf_directory)
    report_path = Path(report_path).resolve()
    if report_path.exists() or not report_path.parent.is_dir():
        raise ValueError('Report path must be a new file under an existing directory')
    if shutil.disk_usage(prep.LOCAL).free < 500*prep.MIB:
        raise OSError('Need at least 500 MiB free for hybrid outputs')
    split_path = source/'split_manifest.json'
    split = json.loads(split_path.read_text(encoding='utf-8'))
    train_path = cf_evaluation.verify_partition(split['partitions']['train'])
    validation_path = cf_evaluation.verify_partition(split['partitions']['validation'])
    cf,cb,provenance = hybrid.load_components(cb_dir,cf_dir,expected_catalog,expected_content)
    if cb.snapshot['train_end_ms']!=split['protocol']['train_end_inclusive_ms']:
        raise ValueError('Frozen training snapshot cutoff differs from split')
    # Hash existing artifact bytes for preservation; never interpret prior test
    # result JSON or read test interaction CSV until selection is persisted.
    protected_paths = {p for directory in (cf_dir,cb_dir,source) for p in directory.rglob('*')
                       if p.is_file() and p != Path(split['partitions']['test']['path'])}
    protected = content_evaluation.fingerprints(sorted(protected_paths))
    before_models = frozen_fingerprint(cf,cb)
    directory = Path(tempfile.mkdtemp(prefix='hybrid-',dir=prep.LOCAL))
    environment = {'python':platform.python_version(),'numeric_threads':1,
                   'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
                   'no_packages_installed':True}
    prep.write_json(directory/'environment.json',environment)
    rows = list(prep.iter_rows(validation_path))
    if len(rows)!=split['partitions']['validation']['interactions']:
        raise ValueError('Validation count differs from manifest')
    begin,end = split['protocol']['train_end_inclusive_ms'],split['protocol']['validation_end_inclusive_ms']
    validation = {}
    rank = popularity.build_ranking(cb.snapshot)
    cf_name,cb_name = provenance['cf_configuration'],provenance['content_configuration']
    validation['count'] = content_evaluation.evaluate(rows,rank,cb.snapshot,cb.snapshot['seen'],begin,end,
                                    directory/'validation_predictions_count.csv')
    for name,model in ((cf_name,cf),(cb_name,cb)):
        validation[name] = content_evaluation.evaluate(rows,rank,cb.snapshot,cb.snapshot['seen'],begin,end,
                                    directory/f'validation_predictions_{name}.csv',model)
    candidates,grid_resources = evaluate_grid(rows,cf,cb,begin,end,directory)
    validation.update(candidates)
    decision = decide_default(validation,cb_name)
    decision.update({'rank_constant':hybrid.RANK_CONSTANT,'frozen_component_fingerprints':before_models})
    prep.write_json(directory/'validation_selection.json',decision)
    if frozen_fingerprint(cf,cb)!=before_models:
        raise RuntimeError('Component models changed during validation')
    # Only now inspect prior controls and test interactions.
    count_prior = json.loads((source/'results.json').read_text(encoding='utf-8'))
    cf_prior = json.loads((cf_dir/'results.json').read_text(encoding='utf-8'))
    cb_prior = json.loads((cb_dir/'results.json').read_text(encoding='utf-8'))
    for name,prior in (('count',count_prior),(cf_name,cf_prior),(cb_name,cb_prior)):
        cf_evaluation.assert_same_metrics(validation[name],prior['validation'][name])
    if (cb_prior['split_manifest_sha256']!=prep.sha256(split_path)
            or cf_prior['source_split_manifest_sha256']!=prep.sha256(split_path)):
        raise ValueError('Source component evaluation protocols differ')
    test_path = cf_evaluation.verify_partition(split['partitions']['test'])
    test_before = content_evaluation.fingerprints([test_path])
    test_rows = list(prep.iter_rows(test_path))
    if len(test_rows)!=split['partitions']['test']['interactions']:
        raise ValueError('Test count differs from manifest')
    seen = popularity.extend_history(cb.snapshot['seen'],rows,end)
    # Fresh usage counters; all trained arrays and seed histories are shared.
    cf_test = item_cf.ItemRecommender(cf.matrix,cf.users,cf.items,cf.graph,cf.snapshot)
    cb_test = content.ContentRecommender(cb.positive,cb.users,cb.items,cb.features,cb.snapshot)
    test = {'count':content_evaluation.evaluate(test_rows,rank,cb.snapshot,seen,end,None,directory/'test_predictions_count.csv')}
    for name,model,prior in ((cf_name,cf_test,cf_prior),(cb_name,cb_test,cb_prior)):
        test[name] = content_evaluation.evaluate(test_rows,rank,cb.snapshot,seen,end,None,
                                    directory/f'test_predictions_{name}.csv',model)
        cf_evaluation.assert_same_metrics(test[name],prior['test'][name])
    cf_evaluation.assert_same_metrics(test['count'],count_prior['test']['count'])
    model = hybrid.HybridRecommender(cf,cb,decision['selected_cf_weight'])
    model.load_feature_names(cb_dir,cb_name)
    with (directory/'test_fusion_evidence.jsonl').open('x',encoding='utf-8',newline='\n') as output, \
         (directory/'test_reason_evidence_sample.jsonl').open('x',encoding='utf-8',newline='\n') as rich:
        writer = EvidenceWriter(model,output,rich)
        value = evaluation.evaluate_window(test_rows,rank,cb.snapshot,seen,end,
                    prediction_path=directory/f"test_predictions_{decision['selected_hybrid']}.csv",recommender=writer)
    value['personalization'] = model.usage_summary()
    resource = value['resources']
    resource['callback_with_evidence_median_microseconds'] = resource.pop('recommendation_latency_median_microseconds')
    resource['callback_with_evidence_p95_microseconds'] = resource.pop('recommendation_latency_p95_microseconds')
    times = sorted(model.latencies_ns)
    resource['recommendation_latency_median_microseconds'] = statistics.median(times)/1000
    resource['recommendation_latency_p95_microseconds'] = times[math.ceil(.95*len(times))-1]/1000
    resource['latency_scope'] = 'live component extraction plus fusion; excludes evidence export'
    value['evidence'] = {'fusion_trace_rows':writer.rows,'rich_evidence_rows':writer.rich_rows,
                         'rich_evidence_user_limit':writer.rich_user_limit}
    test[decision['selected_hybrid']] = value
    if frozen_fingerprint(cf,cb)!=before_models:
        raise RuntimeError('A frozen component changed during test evaluation')
    if (content_evaluation.fingerprints(sorted(protected_paths))!=protected
            or content_evaluation.fingerprints([test_path])!=test_before):
        raise RuntimeError('An existing input/model artifact changed')
    subset = prep.require_local(split['source']['path'])
    if prep.sha256(subset)!=split['source']['sha256']:
        raise RuntimeError('Existing subset checksum differs')
    component_files = [cb_dir/name for name in ('validation_selection.json','training_snapshot.json','id_mappings.json',
                                                'positive_training.npz',f'features_{cb_name}.npz')]
    component_files += [cf_dir/name for name in ('validation_selection.json','id_mappings.json','positive_training.npz',f'neighbors_{cf_name}.npz')]
    df = int(cb_name.split('_')[1][2:])
    component_files += [cb_dir/name for name in (f'vectorizers_df{df}.joblib',f'title_df{df}.npz',f'category_df{df}.npz')]
    manifest = {**provenance,'rank_constant':hybrid.RANK_CONSTANT,
                'selected_cf_weight':decision['selected_cf_weight'],'default_model':decision['default_model'],
                'score_type':'normalized_weighted_rrf','scores_are_probabilities':False,
                'component_file_sha256':{str(path):prep.sha256(path) for path in component_files}}
    prep.write_json(directory/'hybrid_manifest.json',manifest)
    prep.write_json(directory/'input_integrity.json',{'protected_sources':protected,'test':test_before,'unchanged':True})
    result = {'status':'complete','created_utc':datetime.now(timezone.utc).isoformat(),'algorithm_version':'1.0',
              'run_directory':str(directory),'components':provenance,'selection':decision,
              'validation':validation,'test':test,'environment':environment,'grid_resources':grid_resources,
              'integrity':{'all_original_controls_identical':True,'component_models_unchanged':True,
                           'source_files_unchanged':True,'test_read_after_default_decision':True,
                           'existing_models_retrained':False,'protected_files':len(protected_paths)+1},
              'resources':{'elapsed_seconds':time.perf_counter()-started,
                           **prep.load_local('inspect_ratings').process_memory(),
                           'retained_artifact_bytes_before_results':sum(p.stat().st_size for p in directory.iterdir() if p.is_file())},
              'implementation_sha256':{name:prep.sha256(Path(__file__).with_name(name)) for name in
                  ('hybrid_ranker.py','evaluate_hybrid.py','item_cf.py','content_tfidf.py','evaluate_popularity.py')}}
    prep.write_json(directory/'results.json',result)
    with report_path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(report_markdown(result))
    print(json.dumps({'run_directory':str(directory),'decision':decision,'test':value['segments']['overall'],
                      'resources':result['resources']},indent=2),flush=True)
    return result


def report_markdown(r):
    selection = r['selection']
    selected = selection['selected_hybrid']
    cb,cf = r['components']['content_configuration'],r['components']['cf_configuration']
    lines = ['# SmartShop-AI weighted RRF hybrid results','',
             f"Best hybrid: **{selected}**, CF weight {selection['selected_cf_weight']:.2f}; content weight {1-selection['selected_cf_weight']:.2f}. Fixed rank constant: 60.",
             f"Default decision: **{selection['default_model']}**. Strict validation improvement: **{selection['strict_validation_improvement']}**.",'',
             '## Validation','', '| Model | Recall@10 | NDCG@10 | Catalog coverage | Personalized users | Fallback slots |',
             '|---|---:|---:|---:|---:|---:|']
    for name in ['count',cf,cb,*[hybrid.name_for(w) for w in hybrid.CF_WEIGHTS]]:
        v = r['validation'][name]; m=v['segments']['overall'];u=v.get('personalization',{})
        lines.append(f"| {name} | {m['recall_at_10']:.8f} | {m['ndcg_at_10']:.8f} | {m['catalog_coverage_at_10']:.8f} | {u.get('fraction_users_personalized',0):.2%} | {u.get('fraction_fallback_slots',1):.2%} |")
    lines += ['', '## Frozen test comparison','',
              '| Model | Recall@10 | NDCG@10 | Catalog coverage | Hits | Personalized users | Fallback slots |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for name in ['count',cf,cb,selected]:
        v=r['test'][name];m=v['segments']['overall'];u=v.get('personalization',{})
        lines.append(f"| {name} | {m['recall_at_10']:.8f} | {m['ndcg_at_10']:.8f} | {m['catalog_coverage_at_10']:.8f} | {m['hits_at_10']} | {u.get('fraction_users_personalized',0):.2%} | {u.get('fraction_fallback_slots',1):.2%} |")
    lines += ['', '## Challenger test segments','', '| Segment | Positive users | Recall@10 | NDCG@10 |', '|---|---:|---:|---:|']
    for name in ['overall','warm_users','cold_users',*evaluation.FOUR_SEGMENTS,'history_0','history_1_2','history_3_4','history_5_plus']:
        m=r['test'][selected]['segments'][name]
        number=lambda value:'undefined' if value is None else f'{value:.8f}'
        lines.append(f"| {name} | {m['evaluated_users']} | {number(m['recall_at_10'])} | {number(m['ndcg_at_10'])} |")
    resources=r['resources'];q=r['test'][selected]['resources']
    lines += ['', '## Runtime and integrity','',
              f"Pipeline: {resources['elapsed_seconds']:.3f} seconds; process peak working set {resources['peak_working_set_bytes']/prep.MIB:.2f} MiB; retained output before result/report writes {resources['retained_artifact_bytes_before_results']/prep.MIB:.2f} MiB.",
              f"Live hybrid query median {q['recommendation_latency_median_microseconds']/1000:.3f} ms; p95 {q['recommendation_latency_p95_microseconds']/1000:.3f} ms, excluding evidence-file export.",'',
              f"Ignored run: `{r['run_directory']}`. Component models are referenced by fingerprint/hash, not retrained or overwritten.",'',
              'Count, CF, and content validation/test cohorts, segment metrics, and prediction hashes reproduce exactly. Selection and the strict default gate were saved before test interaction reads. No post-test weight changes or automatic threshold relaxation occurred. Test compares the locked challenger even if content wins the default gate. Default means a saved selection manifest, not a deployed service.','',
              'All candidate products stay within the 11,012 training catalog. Training-only profiles and frozen scores are preserved; validation changes only test seen masks. Personalization/fallback rates include all holdout users, while ranking metrics/catalog coverage use the existing positive-user cohort. Cold products remain unreachable.','',
              'Full per-item fusion traces and a bounded rich-evidence sample are saved locally. Evidence identifies positive component support, ordinal ranks, raw scores, effective weights, rank contributions, training-liked CF seeds and shared TF-IDF features. Popularity is applied once after fusion and is never counted as personalized evidence. Scores are ranking values, not probabilities or confidence percentages.','',
              'Metadata snapshot timing, retrospective five-core selection, repeated use of validation for component/weight selection, and loss of score magnitude in RRF remain limitations. Point-estimate gains are not significance or online-benefit claims. See `docs/hybrid_strategy.md` for algorithm, tests, and reproduction. No backend/frontend, downloads, new dependencies, or Git configuration/commit/push actions were performed. Stop for review.','']
    return '\n'.join(lines)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation',type=Path,required=True)
    parser.add_argument('--content',type=Path,required=True)
    parser.add_argument('--cf',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True,help='New output filename')
    args=parser.parse_args()
    with threadpool_limits(limits=1):
        run(args.evaluation,args.content,args.cf,args.report)
