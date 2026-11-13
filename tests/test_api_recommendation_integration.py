"""Real frozen-bundle parity, evidence and privacy under training-only masks."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app.config import LOCAL, POINTER, ROOT, Settings
from backend.app.main import create_app
from backend.app.services.model_registry import sha256

if str(ROOT/'scripts') not in sys.path:sys.path.insert(0,str(ROOT/'scripts'))
import content_tfidf
import item_cf
import popularity_baseline


class FrozenRecommendationIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not POINTER.exists():
            raise unittest.SkipTest('Prepare the local catalog before frozen-bundle integration')
        cls.temp=tempfile.TemporaryDirectory(prefix='backend-stage2-test-',dir=LOCAL)
        cls.settings=replace(Settings.from_environment(),runtime_directory=Path(cls.temp.name)/'runtime')
        cls.patches=[patch.object(popularity_baseline,'fit_training',side_effect=AssertionError('No training')),
                     patch.object(item_cf,'positive_matrix',side_effect=AssertionError('No positive rebuild')),
                     patch.object(item_cf,'build_neighbors',side_effect=AssertionError('No CF fitting')),
                     patch.object(content_tfidf,'fit_fields',side_effect=AssertionError('No IDF fitting'))]
        for p in cls.patches:p.start()
        cls.app=create_app(cls.settings)
        cls.client=TestClient(cls.app)
        cls.client.__enter__()
        if not cls.app.state.ready:raise AssertionError('Frozen application did not become ready')
        cls.aliases=[p['public_user_id'] for p in cls.client.get('/api/v1/demo/profiles').json()['items']]
        cls.model=cls.app.state.registry.model
        cls.snapshot_fingerprint=popularity_baseline.fingerprint(cls.model.snapshot)
        cls.positive_fingerprint=item_cf.array_fingerprint(cls.model.cf.matrix,cls.model.cf.users,cls.model.items)
        cls.saved=json.loads((cls.settings.hybrid_directory/'results.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        if popularity_baseline.fingerprint(cls.model.snapshot)!=cls.snapshot_fingerprint:
            raise AssertionError('Serving changed training history')
        if item_cf.array_fingerprint(cls.model.cf.matrix,cls.model.cf.users,cls.model.items)!=cls.positive_fingerprint:
            raise AssertionError('Serving changed positive seeds')
        if sha256(cls.settings.database)!=cls.settings.database_sha256:
            raise AssertionError('Serving changed catalog database')
        cls.client.__exit__(None,None,None)
        for p in reversed(cls.patches):p.stop()
        cls.temp.cleanup()

    def get_recs(self,alias,name='hybrid'):
        r=self.client.get('/api/v1/users/'+alias+'/recommendations',params={'model':name})
        self.assertEqual(r.status_code,200,r.text)
        user=self.app.state.identities.resolve(alias)[0]
        self.assertNotIn(user,r.text)
        self.assertNotIn(str(ROOT),r.text)
        return r.json()

    def explain(self,rec,item):
        r=self.client.get('/api/v1/recommendations/'+rec['batch_id']+'/items/'+item['product']['product_id']+'/explanation')
        self.assertEqual(r.status_code,200,r.text)
        e=r.json();self.assertEqual(e['ranking_score'],item['score'])
        self.assertEqual(e['source'],item['source']);self.assertEqual(e['product'],item['product'])
        self.assertNotIn(str(ROOT),r.text)
        return e

    def test_all_twelve_profiles_four_native_models_exact_parity(self):
        for alias in self.aliases:
            user,_=self.app.state.identities.resolve(alias)
            seen=frozenset(self.model.snapshot['seen'][user])
            for name in ('hybrid','count','cf','content'):
                with self.subTest(model=name):
                    with self.app.state.registry.inference_lock:
                        direct=(popularity_baseline.recommend(self.model.fallback,seen,10) if name=='count' else
                                {'hybrid':self.model,'cf':self.model.cf,'content':self.model.content}[name](user,seen,10))
                    rec=self.get_recs(alias,name)
                    self.assertEqual([(p['product']['product_id'],p['score']) for p in rec['items']],direct)
                    self.assertEqual(len(direct),10)
                    self.assertFalse(seen&{p for p,_ in direct})
                    self.assertTrue(all(p['product']['recommendation_eligible'] for p in rec['items']))

    def test_all_hybrid_items_and_native_support_explanations(self):
        for alias in self.aliases:
            user,_=self.app.state.identities.resolve(alias)
            for name in ('hybrid','cf','content','count'):
                rec=self.get_recs(alias,name)
                for item in rec['items'][:10 if name=='hybrid' else 3]:
                    e=self.explain(rec,item)
                    self.assertNotIn(user,json.dumps(e))
                    if 'fusion' in e:
                        f=e['fusion']
                        self.assertAlmostEqual(f['cf_rank_contribution']+f['content_rank_contribution'],e['ranking_score'],places=12)
                        self.assertEqual(f['configured_cf_weight'],0.5)
                    if name=='cf' and 'cf_support' in e:
                        self.assertAlmostEqual(e['cf_support']['total_seed_similarity'],e['ranking_score'],places=12)
                    if name=='content' and 'content_support' in e:
                        self.assertAlmostEqual(e['content_support']['total_feature_contribution'],e['ranking_score'],places=6)
                    for seed in e.get('cf_support',{}).get('seed_contributions',[]):
                        self.assertIn(seed['product']['product_id'],self.model.snapshot['seen'][user])
                        row=self.model.cf.user_index[user]
                        col=self.model.index[seed['product']['product_id']]
                        self.assertEqual(self.model.cf.matrix[row,col],1)

    def test_saved_aggregate_metrics_exact_without_internal_fields(self):
        r=self.client.get('/api/v1/metrics/models');self.assertEqual(r.status_code,200)
        data=r.json();self.assertEqual(data['candidate_products'],11012)
        names={'count':'count','cf':'item_cf_k50_lambda10','content':'tfidf_df2_title80','hybrid':'hybrid_cf50'}
        self.assertEqual(len(data['models']),8)
        for row in data['models']:
            saved=self.saved[row['split']][names[row['model']]]
            for segment in row['segments']:
                source=saved['segments'][segment['segment']]
                for field in ('recall_at_10','ndcg_at_10','catalog_coverage_at_10','evaluated_users'):
                    self.assertEqual(segment[field],source[field])
        for private in ('run_directory','implementation_sha256','predictions','resources','training_fingerprint'):
            self.assertNotIn(private,r.text)

    def test_new_demo_user_count_only_and_unknown_alias(self):
        r=self.client.post('/api/v1/demo/users',json={});self.assertEqual(r.status_code,201)
        alias=r.json()['public_user_id']
        rec=self.client.get('/api/v1/users/'+alias+'/recommendations?model=content').json()
        self.assertTrue(rec['cold_start']);self.assertEqual(rec['model'],'count')
        self.assertEqual(rec['fallback_count'],10)
        self.assertEqual([(p['product']['product_id'],p['score']) for p in rec['items']],
                         popularity_baseline.recommend(self.model.fallback,set(),10))
        self.assertTrue(self.explain(rec,rec['items'][0])['count_evidence'])
        self.assertEqual(self.client.get('/api/v1/users/not_created/recommendations').status_code,404)

    def test_similar_native_parity_and_actual_zero_vector(self):
        zero=next(self.model.items[i] for i in range(len(self.model.items))
                  if not self.model.content.features[i:i+1].nnz)
        for product in (self.model.items[0],self.model.items[100],zero):
            r=self.client.get('/api/v1/products/'+product+'/similar');self.assertEqual(r.status_code,200)
            self.assertEqual([(p['product']['product_id'],p['score']) for p in r.json()['items']],
                             self.model.content.similar_items(product,10))
        self.assertEqual(self.client.get('/api/v1/products/'+zero+'/similar').json()['items'],[])

    def test_real_concurrent_profile_batch_evidence_consistency(self):
        def request(alias):
            rec=self.get_recs(alias)
            return rec,self.explain(rec,rec['items'][0])
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(request,self.aliases))
        self.assertEqual(len({rec['batch_id'] for rec,e in results}),12)
        for rec,e in results:
            user,_=self.app.state.identities.resolve(rec['public_user_id'])
            for seed in e.get('cf_support',{}).get('seed_contributions',[]):
                self.assertIn(seed['product']['product_id'],self.model.snapshot['seen'][user])

    def test_recommendation_startup_explanation_and_metrics_do_not_read_holdout(self):
        original=Path.open
        def guard(path,*args,**kwargs):
            if path.suffix=='.csv' or path.suffix=='.jsonl':
                raise AssertionError('Serving must not read ratings, prediction rows or metadata exports after checksum validation')
            return original(path,*args,**kwargs)
        # Metadata is checksummed at startup; no rows are parsed. Allow its bytes.
        def allow_metadata(path,*args,**kwargs):
            if path.resolve()==self.settings.metadata.resolve():return original(path,*args,**kwargs)
            return guard(path,*args,**kwargs)
        with patch.object(Path,'open',allow_metadata):
            with TestClient(create_app(self.settings)) as client:
                self.assertEqual(client.get('/api/v1/health/ready').status_code,200)
                r=client.get('/api/v1/users/'+self.aliases[0]+'/recommendations');self.assertEqual(r.status_code,200)
                rec=r.json();p=rec['items'][0]['product']['product_id']
                self.assertEqual(client.get('/api/v1/recommendations/'+rec['batch_id']+'/items/'+p+'/explanation').status_code,200)
                self.assertEqual(client.get('/api/v1/metrics/models').status_code,200)
