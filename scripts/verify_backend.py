"""Read-only Stage 1 endpoint audit; saves only aggregate results locally."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from backend.app.config import Settings, local_path
from backend.app.main import create_app
from backend.app.services.model_registry import sha256
from inspect_ratings import process_memory


def run(report):
    started=time.perf_counter()
    settings=Settings.from_environment()
    app=create_app(settings)
    with TestClient(app) as client:
        if client.get('/api/v1/health/ready').status_code!=200:
            raise ValueError('Backend did not become ready')
        first=client.get('/api/v1/products').json()['items'][0]
        paths={
            'liveness':('/api/v1/health/live',{}),
            'readiness':('/api/v1/health/ready',{}),
            'product_page':('/api/v1/products',{}),
            'product_search':('/api/v1/products',{'q':first['title'][:24]}),
            'category_filter':('/api/v1/products',{'category':(first['categories'] or [first['main_category']])[0]}),
            'product_detail':('/api/v1/products/'+first['product_id'],{}),
            'demo_profiles':('/api/v1/demo/profiles',{}),
        }
        timings={}
        for name,(path,params) in paths.items():
            samples=[]
            for _ in range(50):
                before=time.perf_counter_ns()
                response=client.get(path,params=params)
                samples.append((time.perf_counter_ns()-before)/1e6)
                if response.status_code!=200:
                    raise AssertionError('API audit request failed')
            timings[name]={'requests':len(samples),'median_ms':statistics.median(samples),
                           'p95_ms':sorted(samples)[47]}
        with app.state.catalog.repository.connection() as con:
            counts=con.execute('SELECT COUNT(*),SUM(recommendation_eligible),SUM(title_available) FROM products').fetchone()
            activities=dict(con.execute('SELECT activity,COUNT(*) FROM demo_profiles GROUP BY activity'))
            private=con.execute('SELECT COUNT(*) FROM dataset_user_aliases').fetchone()[0]
            info=dict(con.execute('SELECT key,value FROM application_manifest'))
        if tuple(counts)!=(12635,11012,12634) or private!=12:
            raise AssertionError('Application aggregates differ from approval')
        model=app.state.registry.model
        report_data={'created_utc':datetime.now(timezone.utc).isoformat(),
                     'status':'passed','measurement':'in-process TestClient including HTTPX/ASGI/serialization; no socket transport',
                     'products':counts[0],'eligible':counts[1],'usable_titles':counts[2],
                     'demo_profiles':private,'profile_activity_counts':activities,
                     'history_policy':info['history_policy'],
                     'held_out_interactions_loaded':info['held_out_interactions_loaded'],
                     'startup_seconds':app.state.startup_seconds,
                     'elapsed_seconds':time.perf_counter()-started,
                     'memory':process_memory(),'database_bytes':settings.database.stat().st_size,
                     'database_sha256':sha256(settings.database),
                     'metadata_sha256':sha256(settings.metadata),'endpoint_latency':timings,
                     'stage2_inference_calls':model.usage['users']}
    if report_data['stage2_inference_calls']!=0:
        raise AssertionError('Stage 1 audit unexpectedly performed recommendations')
    report=local_path(report)
    with report.open('x',encoding='utf-8') as stream:
        json.dump(report_data,stream,indent=2)
    print(json.dumps(report_data,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True,help='New JSON report under data/local; never overwritten')
    run(parser.parse_args().report)
