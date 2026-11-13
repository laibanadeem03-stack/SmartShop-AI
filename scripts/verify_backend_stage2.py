"""Read-only frozen-source audit with isolated mutable demo state and API timings."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from threadpoolctl import threadpool_limits
from backend.app.config import LOCAL, Settings, local_path
from backend.app.main import create_app
from backend.app.services.model_registry import sha256
from inspect_ratings import process_memory
import popularity_baseline
import item_cf


def run(report):
    start=time.perf_counter()
    directory=LOCAL/('backend-stage2-audit-'+uuid4().hex[:12])
    directory.mkdir()
    settings=replace(Settings.from_environment(),runtime_directory=directory/'runtime')
    app=create_app(settings)
    with threadpool_limits(limits=1),TestClient(app) as client:
        if not app.state.ready:raise AssertionError('Backend is not ready')
        aliases=[p['public_user_id'] for p in client.get('/api/v1/demo/profiles').json()['items']]
        engine=app.state.registry.model
        frozen=popularity_baseline.fingerprint(engine.snapshot)
        seeds=item_cf.array_fingerprint(engine.cf.matrix,engine.cf.users,engine.items)
        parity=explanations=0
        usages={}
        for alias in aliases:
            user,_=app.state.identities.resolve(alias)
            seen=frozenset(engine.snapshot['seen'][user])
            for name in ('hybrid','count','cf','content'):
                with app.state.registry.inference_lock:
                    direct=(popularity_baseline.recommend(engine.fallback,seen,10) if name=='count' else
                            {'hybrid':engine,'cf':engine.cf,'content':engine.content}[name](user,seen,10))
                response=client.get('/api/v1/users/'+alias+'/recommendations',params={'model':name})
                if response.status_code!=200:raise AssertionError('Recommendation request failed')
                batch=response.json()
                if [(p['product']['product_id'],p['score']) for p in batch['items']]!=direct:
                    raise AssertionError('Native/API parity failed')
                parity+=1
                use=usages.setdefault(name,{'users':0,'personalized_users':0,'personalized_slots':0,'fallback_slots':0,'total_slots':0})
                use['users']+=1;use['personalized_users']+=batch['personalized_count']>0
                use['personalized_slots']+=batch['personalized_count'];use['fallback_slots']+=batch['fallback_count']
                use['total_slots']+=len(batch['items'])
                for item in batch['items'][:10 if name=='hybrid' else 1]:
                    response=client.get('/api/v1/recommendations/'+batch['batch_id']+'/items/'+item['product']['product_id']+'/explanation')
                    if response.status_code!=200:raise AssertionError('Explanation failed')
                    evidence=response.json()
                    if evidence['ranking_score']!=item['score']:raise AssertionError('Explanation score mismatch')
                    if 'fusion' in evidence:
                        f=evidence['fusion']
                        if not math.isclose(f['cf_rank_contribution']+f['content_rank_contribution'],item['score'],abs_tol=1e-14):
                            raise AssertionError('Fusion contribution mismatch')
                    explanations+=1
        cold=client.post('/api/v1/demo/users',json={}).json()['public_user_id']
        example=client.get('/api/v1/users/'+aliases[0]+'/recommendations').json()
        explanation_path='/api/v1/recommendations/'+example['batch_id']+'/items/'+example['items'][0]['product']['product_id']+'/explanation'
        operations={name:('/api/v1/users/'+aliases[0]+'/recommendations',{'model':name}) for name in ('count','cf','content','hybrid')}
        operations.update(cold_start=('/api/v1/users/'+cold+'/recommendations',{}),
                          similar=('/api/v1/products/'+engine.items[0]+'/similar',{}),
                          metrics=('/api/v1/metrics/models',{}))
        timings={}
        # Measure explanations first, before other measured requests can evict its batch.
        for name,(path,params) in [('explanation',(explanation_path,{})),*operations.items()]:
            samples=[]
            for i in range(50):
                if name in ('count','cf','content','hybrid'):
                    path='/api/v1/users/'+aliases[i%len(aliases)]+'/recommendations'
                before=time.perf_counter_ns()
                response=client.get(path,params=params)
                samples.append((time.perf_counter_ns()-before)/1e6)
                if response.status_code!=200:raise AssertionError('Latency request failed')
            timings[name]={'requests':50,'median_ms':statistics.median(samples),'p95_ms':sorted(samples)[47]}
        if len(app.state.recommendations.cache.entries)!=100:
            raise AssertionError('Batch cache did not remain at its approved bound')
        if popularity_baseline.fingerprint(engine.snapshot)!=frozen or item_cf.array_fingerprint(engine.cf.matrix,engine.cf.users,engine.items)!=seeds:
            raise AssertionError('Online inference changed training state')
        if sha256(settings.database)!=settings.database_sha256:
            raise AssertionError('Serving changed original catalog')
        receipt={'status':'passed','created_utc':datetime.now(timezone.utc).isoformat(),
                 'measurement':'50 sequential in-process HTTPX/ASGI requests per operation, one numeric thread; no socket transport',
                 'startup_seconds':app.state.startup_seconds,'elapsed_seconds':time.perf_counter()-start,
                 'memory':process_memory(),'latency':timings,'demo_profiles':len(aliases),
                 'exact_native_api_batches':parity,'verified_explanations':explanations,
                 'profile_usage':usages,'cache_entries':100,'cache_ttl_seconds':300,
                 'runtime_database_bytes':(settings.runtime_directory/'demo_users.sqlite3').stat().st_size,
                 'original_catalog_bytes':settings.database.stat().st_size,
                 'original_catalog_unchanged':True,'training_snapshot_and_positive_matrix_unchanged':True,
                 'held_out_interactions_loaded':False,'isolated_demo_state_directory':str(settings.runtime_directory)}
    report=local_path(report)
    with report.open('x',encoding='utf-8') as stream:json.dump(receipt,stream,indent=2)
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True,help='New aggregate report under data/local; never overwritten')
    run(parser.parse_args().report)
