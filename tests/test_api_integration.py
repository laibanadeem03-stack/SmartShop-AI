"""Read-only integration against the explicitly prepared local application DB."""
import json
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app.config import POINTER, ROOT, Settings
from backend.app.main import create_app
from backend.app.services.model_registry import sha256

if str(ROOT/'scripts') not in sys.path:
    sys.path.insert(0,str(ROOT/'scripts'))
import content_tfidf
import item_cf
import popularity_baseline


class LocalApiIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not POINTER.exists():
            raise unittest.SkipTest('Prepare local application data before running real-artifact integration')
        cls.settings=Settings.from_environment()
        cls.metadata=content_tfidf.load_metadata(cls.settings.metadata,cls.settings.metadata_sha256)
        manifest=json.loads((cls.settings.hybrid_directory/'hybrid_manifest.json').read_text(encoding='utf-8'))
        cls.sources={str(cls.settings.metadata):sha256(cls.settings.metadata),
                     str(cls.settings.database):sha256(cls.settings.database),**manifest['component_file_sha256']}
        cls.patches=[patch.object(popularity_baseline,'fit_training',side_effect=AssertionError('No training allowed')),
                     patch.object(item_cf,'positive_matrix',side_effect=AssertionError('No matrix rebuild allowed')),
                     patch.object(item_cf,'build_neighbors',side_effect=AssertionError('No neighbor fitting allowed')),
                     patch.object(content_tfidf,'fit_fields',side_effect=AssertionError('No text fitting allowed'))]
        for p in cls.patches:p.start()
        cls.app=create_app(cls.settings)
        cls.client=TestClient(cls.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None,None,None)
        for p in reversed(cls.patches):p.stop()
        for name,digest in cls.sources.items():
            if sha256(__import__('pathlib').Path(name))!=digest:
                raise AssertionError('A frozen source changed during API integration')

    def test_actual_database_and_model_ready(self):
        self.assertEqual(self.client.get('/api/v1/health/ready').status_code,200)
        self.assertEqual(len(self.app.state.registry.model.items),11012)
        self.assertEqual(self.app.state.registry.model.cf_weight,0.5)

    def test_all_products_original_metadata_and_eligibility(self):
        ids=set(); eligible=unavailable=0
        for page in range(1,128):
            response=self.client.get('/api/v1/products',params={'page':page,'page_size':100})
            self.assertEqual(response.status_code,200)
            data=response.json();self.assertEqual(data['total'],12635)
            for product in data['items']:
                identifier=product['product_id'];self.assertNotIn(identifier,ids);ids.add(identifier)
                original=self.metadata[identifier]
                self.assertEqual(product['main_category'],original['main_category'])
                self.assertEqual(product['categories'],original['categories'])
                self.assertEqual(product['title'],original['title'] if product['title_available'] else 'Title unavailable')
                self.assertEqual(product['recommendation_eligible'],identifier in self.app.state.registry.model.index)
                eligible+=product['recommendation_eligible'];unavailable+=not product['title_available']
        self.assertEqual((len(ids),eligible,unavailable),(12635,11012,1))

    def test_curated_profiles_training_only_and_private(self):
        response=self.client.get('/api/v1/demo/profiles')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['total'],12)
        self.assertEqual(len({p['public_user_id'] for p in response.json()['items']}),12)
        self.assertNotIn('dataset_user_id',response.text)
        users=self.app.state.registry.model.snapshot['seen']
        self.assertTrue(all(user not in response.text for user in users))
        self.assertNotIn(str(ROOT),response.text)

    def test_actual_search_category_and_detail(self):
        record=next(r for r in self.metadata.values() if content_tfidf.clean_text(r['title']) and r['categories'])
        response=self.client.get('/api/v1/products',params={'q':record['title'][:60],'category':record['categories'][0]})
        self.assertGreaterEqual(response.json()['total'],1)
        detail=self.client.get('/api/v1/products/'+record['parent_asin'])
        self.assertEqual(detail.status_code,200)
        self.assertEqual(detail.json()['title'],record['title'])

    def test_serving_does_not_read_holdout_csvs(self):
        from pathlib import Path
        original_open=Path.open
        def guarded_open(path,*args,**kwargs):
            if path.name in ('test.csv','validation.csv','ratings_subset.csv'):
                raise AssertionError('Serving must not read held-out interactions or subset')
            return original_open(path,*args,**kwargs)
        # A fresh startup is included, not only already-loaded endpoint calls.
        with patch.object(Path,'open',guarded_open):
            with TestClient(create_app(self.settings)) as client:
                self.assertEqual(client.get('/api/v1/health/ready').status_code,200)
                self.assertEqual(client.get('/api/v1/products').status_code,200)
