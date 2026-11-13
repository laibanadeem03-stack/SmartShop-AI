from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
import json
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from scipy import sparse

from backend.app.config import ORIGIN
from backend.app.errors import ApiError
from backend.app.main import create_app
from backend.app.services.batch_cache import Batch, BatchCache
from backend.app.services.model_registry import sha256
from backend_fixtures import fixture
import popularity_baseline


class RecommendationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp,self.settings,self.registry,self.records=fixture()
        self.app=create_app(self.settings,registry_loader=lambda _:self.registry)
        self.client=TestClient(self.app,raise_server_exceptions=False)
        self.client.__enter__()
        self.alias=self.client.get('/api/v1/demo/profiles').json()['items'][0]['public_user_id']

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()

    def recommendations(self,model='hybrid',alias=None):
        r=self.client.get('/api/v1/users/'+(alias or self.alias)+'/recommendations',params={'model':model})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def explanation(self,batch,item=0):
        p=batch['items'][item]['product']['product_id']
        r=self.client.get('/api/v1/recommendations/'+batch['batch_id']+'/items/'+p+'/explanation')
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def test_default_hybrid_and_training_exclusions(self):
        r=self.client.get('/api/v1/users/'+self.alias+'/recommendations')
        self.assertEqual(r.status_code,200)
        data=r.json();self.assertEqual(data['model'],'hybrid')
        user=self.app.state.identities.resolve(self.alias)[0]
        seen=self.registry.model.snapshot['seen'][user]
        ids=[p['product']['product_id'] for p in data['items']]
        self.assertFalse(set(ids)&seen);self.assertEqual(len(ids),len(set(ids)))
        self.assertNotIn('ITEM04',ids)
        self.assertEqual(data['history_policy'],'training_snapshot')
        self.assertEqual(data['returned_count'],2)  # tiny fixture: no duplicate padding

    def test_api_direct_native_parity_for_all_models(self):
        user=self.app.state.identities.resolve(self.alias)[0]
        model=self.registry.model;seen=frozenset(model.snapshot['seen'][user])
        for name in ('hybrid','count','cf','content'):
            with self.subTest(model=name):
                with self.registry.inference_lock:
                    direct=(popularity_baseline.recommend(model.fallback,seen,10) if name=='count'
                            else {'hybrid':model,'cf':model.cf,'content':model.content}[name](user,seen,10))
                api=self.recommendations(name)
                self.assertEqual([(r['product']['product_id'],r['score']) for r in api['items']],direct)

    def test_determinism_and_no_profile_mutation(self):
        snapshot=deepcopy(self.registry.model.snapshot)
        a=self.recommendations();b=self.recommendations()
        self.assertEqual(a['items'],b['items']);self.assertNotEqual(a['batch_id'],b['batch_id'])
        self.assertEqual(snapshot,self.registry.model.snapshot)
        self.assertIsNone(self.registry.model.last_signals)
        self.assertEqual(self.registry.model.latencies_ns,[])

    def test_hybrid_explanation_exact_fusion_and_support(self):
        rec=self.recommendations();e=self.explanation(rec)
        self.assertEqual(e['ranking_score'],rec['items'][0]['score'])
        self.assertEqual(e['source'],'hybrid_both')
        self.assertAlmostEqual(e['fusion']['cf_rank_contribution']+e['fusion']['content_rank_contribution'],e['ranking_score'])
        self.assertEqual(e['fusion']['configured_cf_weight'],0.5)
        self.assertTrue(e['cf_support']['seed_contributions'])
        self.assertTrue(e['content_support']['top_shared_features'])
        self.assertNotIn('PRIVATE_SYNTHETIC_USER',json.dumps(e))

    def test_native_cf_content_count_explanation_scores(self):
        for name in ('cf','content','count'):
            rec=self.recommendations(name);e=self.explanation(rec)
            self.assertNotIn('fusion',e)
            key=('total_seed_similarity' if name=='cf' else 'total_feature_contribution')
            actual=e['count_evidence']['training_interaction_count'] if name=='count' else e[name+'_support'][key]
            self.assertAlmostEqual(actual,e['ranking_score'],places=6)
            if name=='cf':self.assertNotIn('content_support',e)
            if name=='content':self.assertNotIn('cf_support',e)

    def test_fallback_explanation_is_count_only(self):
        rec=self.recommendations();e=self.explanation(rec,1)
        self.assertEqual(e['source'],'popularity_fallback')
        self.assertEqual(e['ranking_score'],0)
        self.assertEqual(e['score_type'],'fallback_zero')
        self.assertEqual(set(e)&{'cf_support','content_support','fusion'},set())
        self.assertEqual(e['count_evidence']['training_interaction_count'],12)

    def test_missing_cf_signal_renormalizes_content(self):
        self.registry.model.cf.graph=sparse.csr_matrix((3,3),dtype='float32')
        e=self.explanation(self.recommendations())
        self.assertEqual(e['source'],'content_only')
        self.assertEqual(e['fusion']['effective_cf_weight'],0)
        self.assertEqual(e['fusion']['effective_content_weight'],1)

    def test_negative_only_or_zero_positive_profile_uses_fallback(self):
        self.registry.model.cf.matrix.data[:]=0
        self.registry.model.cf.matrix.eliminate_zeros()
        self.registry.model.content.positive=self.registry.model.cf.matrix
        rec=self.recommendations()
        self.assertEqual(rec['personalized_count'],0)
        self.assertTrue(all(p['source']=='popularity_fallback' for p in rec['items']))
        self.assertTrue(self.explanation(rec)['count_evidence'])

    def test_new_users_force_count_for_every_requested_model(self):
        r=self.client.post('/api/v1/demo/users',json={})
        self.assertEqual(r.status_code,201);identity=r.json()
        self.assertEqual(identity['profile_type'],'new_demo')
        direct=popularity_baseline.recommend(self.registry.model.fallback,set(),10)
        for name in ('hybrid','count','cf','content'):
            rec=self.recommendations(name,identity['public_user_id'])
            self.assertTrue(rec['cold_start']);self.assertEqual(rec['model'],'count')
            self.assertEqual(rec['requested_model'],name);self.assertEqual(rec['personalized_count'],0)
            self.assertEqual([(p['product']['product_id'],p['score']) for p in rec['items']],direct)
            self.assertTrue(self.explanation(rec)['count_evidence'])

    def test_new_users_persist_separately_catalog_unchanged(self):
        identity=self.client.post('/api/v1/demo/users',json={}).json()
        self.assertEqual(sha256(self.settings.database),self.settings.database_sha256)
        self.assertEqual(self.client.get('/api/v1/demo/profiles').json()['total'],12)
        with TestClient(create_app(self.settings,registry_loader=lambda _:self.registry)) as other:
            self.assertEqual(other.get('/api/v1/users/'+identity['public_user_id']+'/recommendations').status_code,200)

    def test_creation_rejects_private_identifiers_and_enforces_bound(self):
        r=self.client.post('/api/v1/demo/users',json={'dataset_user_id':'PRIVATE_SYNTHETIC_USER_0'})
        self.assertEqual(r.status_code,422);self.assertNotIn('PRIVATE_SYNTHETIC_USER',r.text)
        self.app.state.identities.demo_repository.limit=1
        self.assertEqual(self.client.post('/api/v1/demo/users',json={}).status_code,201)
        self.assertEqual(self.client.post('/api/v1/demo/users',json={}).status_code,409)

    def test_similar_exact_native_zero_and_outside_catalog(self):
        r=self.client.get('/api/v1/products/ITEM01/similar')
        self.assertEqual(r.status_code,200)
        self.assertEqual([(p['product']['product_id'],p['score']) for p in r.json()['items']],
                         self.registry.model.content.similar_items('ITEM01',10))
        self.assertEqual(self.client.get('/api/v1/products/ITEM03/similar').json()['items'],[])
        self.assertEqual(self.client.get('/api/v1/products/ITEM04/similar').status_code,409)
        self.assertEqual(self.client.get('/api/v1/products/UNKNOWN/similar').status_code,404)

    def test_unknown_user_invalid_model_and_unreturned_item(self):
        self.assertEqual(self.client.get('/api/v1/users/unknown/recommendations').status_code,404)
        self.assertEqual(self.client.get('/api/v1/users/'+self.alias+'/recommendations?model=invalid').status_code,422)
        self.assertEqual(self.client.get('/api/v1/users/'+self.alias+'/recommendations?k=100').status_code,422)
        rec=self.recommendations()
        self.assertEqual(self.client.get('/api/v1/recommendations/'+rec['batch_id']+'/items/ITEM04/explanation').status_code,404)

    def test_batch_expiry_and_eviction_return_sanitized_404(self):
        clock=[0.0]
        self.app.state.recommendations.cache=BatchCache(1,5,clock=lambda:clock[0])
        old=self.recommendations();new=self.recommendations()
        def explain_status(rec):
            return self.client.get('/api/v1/recommendations/'+rec['batch_id']+'/items/'+rec['items'][0]['product']['product_id']+'/explanation')
        self.assertEqual(explain_status(old).status_code,404)
        clock[0]=5
        r=explain_status(new);self.assertEqual(r.status_code,404)
        self.assertNotIn(str(self.settings.database),r.text)

    def test_metrics_allowlist_and_model_filter(self):
        r=self.client.get('/api/v1/metrics/models')
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['models']),8)
        r=self.client.get('/api/v1/metrics/models/content')
        self.assertEqual({m['model'] for m in r.json()['models']},{'content'})
        self.assertEqual(self.client.get('/api/v1/metrics/models/invalid').status_code,422)
        self.assertNotIn(str(self.settings.database),r.text)

    def test_post_cors_limited_to_local_origin(self):
        for origin,expected in [(ORIGIN,200),('http://evil.example',400)]:
            r=self.client.options('/api/v1/demo/users',headers={'Origin':origin,'Access-Control-Request-Method':'POST',
                                                           'Access-Control-Request-Headers':'content-type'})
            self.assertEqual(r.status_code,expected)

    def test_concurrent_requests_and_explanations_never_overlap_inference(self):
        aliases=[p['public_user_id'] for p in self.client.get('/api/v1/demo/profiles').json()['items']]
        active=[0];maximum=[0];guard=threading.Lock()
        original=self.registry.model.prepare
        def delayed(*args):
            with guard:
                active[0]+=1;maximum[0]=max(maximum[0],active[0])
            try:
                time.sleep(0.004)
                return original(*args)
            finally:
                with guard:active[0]-=1
        def request(alias):
            rec=self.recommendations(alias=alias)
            return rec,self.explanation(rec)
        with patch.object(self.registry.model,'prepare',side_effect=delayed):
            with ThreadPoolExecutor(max_workers=6) as pool:
                results=list(pool.map(request,aliases))
        self.assertEqual(maximum[0],1)
        for rec,e in results:
            user=self.app.state.identities.resolve(rec['public_user_id'])[0]
            seeds={p['product']['product_id'] for p in e['cf_support']['seed_contributions']}
            self.assertEqual(seeds,self.registry.model.snapshot['seen'][user])
            self.assertEqual(rec['items'][0]['score'],e['ranking_score'])

    def test_unexpected_inference_failure_sanitized_and_lock_released(self):
        with patch.object(self.registry.model,'prepare',side_effect=RuntimeError('PRIVATE_SYNTHETIC_USER /private/path')):
            r=self.client.get('/api/v1/users/'+self.alias+'/recommendations')
        self.assertEqual(r.status_code,500);self.assertNotIn('PRIVATE_SYNTHETIC_USER',r.text)
        self.assertNotIn('/private/path',r.text)
        self.assertIsNone(self.registry.model.last_signals)
        self.assertTrue(self.registry.inference_lock.acquire(blocking=False))
        self.registry.inference_lock.release()
        self.recommendations()

    def test_raw_training_user_id_is_not_a_public_alias(self):
        user=self.app.state.identities.resolve(self.alias)[0]
        r=self.client.get('/api/v1/users/'+user+'/recommendations')
        self.assertEqual(r.status_code,404)
        self.assertNotIn(user,r.text)

    def test_sanitized_internal_error_preserves_local_cors_only(self):
        with patch.object(self.registry.model,'prepare',side_effect=RuntimeError('PRIVATE_SYNTHETIC_USER')):
            for origin,allowed in [(ORIGIN,True),('http://evil.example',False)]:
                r=self.client.get('/api/v1/users/'+self.alias+'/recommendations',headers={'Origin':origin})
                self.assertEqual(r.status_code,500)
                self.assertEqual(r.headers.get('access-control-allow-origin'),ORIGIN if allowed else None)
                self.assertNotIn('PRIVATE_SYNTHETIC_USER',r.text)

    def test_corrupted_cached_trace_never_yields_fabricated_evidence(self):
        rec=self.recommendations()
        cache=self.app.state.recommendations.cache
        expires,batch=cache.entries[rec['batch_id']]
        batch.traces[0]['cf_rank_contribution']+=0.1
        r=self.client.get('/api/v1/recommendations/'+rec['batch_id']+'/items/'+rec['items'][0]['product']['product_id']+'/explanation')
        self.assertEqual(r.status_code,500)
        self.assertEqual(r.json()['error']['code'],'INTERNAL_ERROR')


class CacheTests(unittest.TestCase):
    def test_defensive_copies_and_no_sliding_expiry(self):
        clock=[0.0];cache=BatchCache(2,3,lambda:clock[0])
        batch=Batch(None,'hybrid',frozenset(),(('ITEM',0.5),),('hybrid_both',),({'score':0.5},))
        key=cache.put(batch);batch.traces[0]['score']=9
        a=cache.get(key);self.assertEqual(a.traces[0]['score'],0.5)
        a.traces[0]['score']=8;clock[0]=2
        self.assertEqual(cache.get(key).traces[0]['score'],0.5)
        clock[0]=3
        with self.assertRaises(ApiError):cache.get(key)

    def test_invalid_or_unbounded_cache_configuration_rejected(self):
        for capacity,ttl in [(0,1),(101,1),(1,0),(1,301)]:
            with self.assertRaises(ValueError):BatchCache(capacity,ttl)
