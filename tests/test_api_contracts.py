import json
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app.config import ORIGIN, Settings, local_path
from backend.app.main import create_app
from backend.app.schemas import ProductQuery
from backend.app.services.model_registry import sha256
from backend_fixtures import fixture
from scripts.prepare_application_data import prepare_database, select_profiles


class ApiContracts(unittest.TestCase):
    def setUp(self):
        self.temp,self.settings,self.registry,self.records=fixture()
        self.app=create_app(self.settings,registry_loader=lambda settings:self.registry)
        self.client=TestClient(self.app,raise_server_exceptions=False)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()

    def test_liveness_readiness(self):
        self.assertEqual(self.client.get('/api/v1/health/live').json(),{'status':'alive'})
        self.assertEqual(self.client.get('/api/v1/health/ready').json(),{'status':'ready','model_version':'hybrid-v1'})

    def test_pagination_and_stable_order(self):
        page=self.client.get('/api/v1/products',params={'page':2,'page_size':2}).json()
        self.assertEqual((page['page'],page['page_size'],page['total']),(2,2,4))
        self.assertEqual([p['product_id'] for p in page['items']],['ITEM03','ITEM04'])
        self.assertEqual(self.client.get('/api/v1/products?page=99').json()['items'],[])

    def test_search_preserves_technical_terms_and_casefolds(self):
        r=self.client.get('/api/v1/products',params={'q':'zx-42 5g'}).json()
        self.assertEqual(r['total'],1)
        self.assertIn('ZX-42',r['items'][0]['title'])

    def test_search_wildcards_are_literal(self):
        self.assertEqual(self.client.get('/api/v1/products',params={'q':'%'}).json()['total'],1)
        self.assertEqual(self.client.get('/api/v1/products',params={'q':"%' OR 1=1 --"}).json()['total'],0)

    def test_category_filter_exact_normalized_no_duplicate_rows(self):
        r=self.client.get('/api/v1/products',params={'category':' CASES '}).json()
        self.assertEqual(r['total'],2)
        self.assertEqual(self.client.get('/api/v1/products',params={'category':'case'}).json()['total'],0)
        self.assertEqual(self.client.get('/api/v1/products',params={'category':'cases','q':'phone'}).json()['total'],1)

    def test_product_details_and_outside_training(self):
        r=self.client.get('/api/v1/products/ITEM01').json()
        self.assertEqual(r['training_interaction_count'],12)
        self.assertEqual(r['training_mean_rating'],4)
        r=self.client.get('/api/v1/products/ITEM04').json()
        self.assertFalse(r['recommendation_eligible'])
        self.assertIsNone(r['training_interaction_count'])

    def test_missing_title_and_null_category(self):
        r=self.client.get('/api/v1/products/ITEM03').json()
        self.assertEqual(r['title'],'Title unavailable')
        self.assertFalse(r['title_available'])
        self.assertIsNone(self.client.get('/api/v1/products/ITEM02').json()['main_category'])

    def test_profiles_no_private_ids(self):
        response=self.client.get('/api/v1/demo/profiles')
        data=response.json()
        self.assertEqual(data['total'],12)
        self.assertEqual({p['activity'] for p in data['items']},{'light','moderate','active'})
        self.assertNotIn('PRIVATE_SYNTHETIC_USER',response.text)
        self.assertNotIn('dataset_user_id',response.text)
        self.assertTrue(all(p['public_user_id'].startswith('demo_') for p in data['items']))

    def test_invalid_queries_have_consistent_redacted_errors(self):
        for params in ({'page':0},{'page_size':101},{'page':'PRIVATE_SYNTHETIC_USER_0'},
                       {'q':'x'*201},{'unexpected':'SECRET'},{'model':'cf'}):
            with self.subTest(params=params):
                r=self.client.get('/api/v1/products',params=params)
                self.assertEqual(r.status_code,422)
                self.assertEqual(r.json()['error']['code'],'INVALID_REQUEST')
                self.assertNotIn('PRIVATE_SYNTHETIC_USER',r.text)
                self.assertNotIn('SECRET',r.text)
                self.assertEqual(r.headers['x-request-id'],r.json()['error']['request_id'])

    def test_unknown_product_error(self):
        r=self.client.get('/api/v1/products/UNKNOWN')
        self.assertEqual(r.status_code,404)
        self.assertEqual(r.json()['error']['code'],'PRODUCT_NOT_FOUND')

    def test_stage2_routes_registered_unknown_subjects_safe(self):
        self.assertEqual(self.client.get('/api/v1/users/unknown/recommendations').status_code,404)
        self.assertEqual(self.client.get('/api/v1/products/ITEM01/similar').status_code,200)
        self.assertEqual(self.client.get('/api/v1/metrics/models').status_code,200)
        self.assertEqual(self.client.get('/api/v1/recommendations/missing/items/ITEM01/explanation').status_code,404)
        self.assertEqual(self.client.post('/api/v1/demo/users',json={}).status_code,201)

    def test_cors_origin_allowlist(self):
        for origin,expected in ((ORIGIN,True),('http://evil.example',False),('http://127.0.0.1:5173',False)):
            r=self.client.options('/api/v1/products',headers={'Origin':origin,'Access-Control-Request-Method':'GET'})
            self.assertEqual(r.status_code,200 if expected else 400)
            self.assertEqual(r.headers.get('access-control-allow-origin'),origin if expected else None)

    def test_openapi_stage1_and_stage2_declared_errors(self):
        spec=self.client.get('/openapi.json').json()
        self.assertEqual(set(spec['paths']),{'/api/v1/products','/api/v1/products/{product_id}',
                          '/api/v1/demo/profiles','/api/v1/health/live','/api/v1/health/ready',
                          '/api/v1/demo/users','/api/v1/users/{public_user_id}/recommendations',
                          '/api/v1/products/{product_id}/similar',
                          '/api/v1/recommendations/{batch_id}/items/{product_id}/explanation',
                          '/api/v1/metrics/models','/api/v1/metrics/models/{model}'})
        self.assertIn('ErrorResponse',spec['components']['schemas'])
        self.assertNotIn(str(self.settings.database),json.dumps(spec))

    def test_unexpected_error_redaction(self):
        with patch.object(self.app.state.catalog,'list_products',side_effect=RuntimeError(str(self.settings.database)+' PRIVATE_SYNTHETIC_USER')):
            r=self.client.get('/api/v1/products')
        self.assertEqual(r.status_code,500)
        self.assertEqual(r.json()['error']['code'],'INTERNAL_ERROR')
        self.assertNotIn(str(self.settings.database),r.text)
        self.assertNotIn('PRIVATE_SYNTHETIC_USER',r.text)

    def test_readonly_database_requests(self):
        digest=sha256(self.settings.database)
        self.client.get('/api/v1/products')
        self.client.get('/api/v1/demo/profiles')
        self.assertEqual(sha256(self.settings.database),digest)
        with self.app.state.catalog.repository.connection() as con:
            with self.assertRaises(sqlite3.OperationalError):
                con.execute('DELETE FROM products')


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp,self.settings,self.registry,self.records=fixture()

    def tearDown(self):
        self.temp.cleanup()

    def test_reproducible_database_and_profile_selection(self):
        other=self.settings.database.parent/'second.sqlite3'
        prepare_database(other,self.records,self.registry,self.settings.metadata_sha256,b'x'*32)
        self.assertEqual(sha256(other),self.settings.database_sha256)

    def test_private_key_changes_aliases_not_training_user_selection(self):
        a=select_profiles(self.registry.model.snapshot,b'x'*32)
        b=select_profiles(self.registry.model.snapshot,b'y'*32)
        self.assertEqual([p['dataset_user_id'] for p in a],[p['dataset_user_id'] for p in b])
        self.assertNotEqual([p['public_user_id'] for p in a],[p['public_user_id'] for p in b])

    def test_preparation_preserves_original_fields_and_has_no_holdout_tables(self):
        with closing(sqlite3.connect(self.settings.database)) as con:
            for p,title,main,cats in con.execute('SELECT parent_asin,title,main_category,categories_json FROM products'):
                self.assertEqual({'parent_asin':p,'title':title,'main_category':main,'categories':json.loads(cats)},self.records[p])
            info=dict(con.execute('SELECT key,value FROM application_manifest'))
            self.assertEqual(info['history_policy'],'training_only')
            self.assertEqual(info['held_out_interactions_loaded'],'false')

    def test_existing_database_never_overwritten(self):
        with self.assertRaises(FileExistsError):
            prepare_database(self.settings.database,self.records,self.registry,self.settings.metadata_sha256,b'x'*32)

    def test_paths_outside_local_rejected(self):
        with self.assertRaises(ValueError):
            local_path(Path.cwd()/'docs'/'private.sqlite3')

    def test_missing_training_product_rejected(self):
        with self.assertRaises(ValueError):
            prepare_database(self.settings.database.parent/'bad.sqlite3',{},self.registry,self.settings.metadata_sha256,b'x'*32)

    def test_tampered_database_disables_readiness_without_leaks(self):
        with closing(sqlite3.connect(self.settings.database)) as con:
            con.execute("UPDATE products SET title='tampered' WHERE parent_asin='ITEM01'")
            con.commit()
        with TestClient(create_app(self.settings,registry_loader=lambda _:self.registry)) as client:
            self.assertEqual(client.get('/api/v1/health/live').status_code,200)
            for path in ('/api/v1/health/ready','/api/v1/products','/api/v1/demo/profiles'):
                r=client.get(path)
                self.assertEqual(r.status_code,503)
                self.assertNotIn(str(self.settings.database),r.text)

    def test_missing_database_is_not_created(self):
        self.settings.database.unlink()
        with TestClient(create_app(self.settings,registry_loader=lambda _:self.registry)) as client:
            self.assertEqual(client.get('/api/v1/health/ready').status_code,503)
        self.assertFalse(self.settings.database.exists())

    def test_metadata_tamper_disables_readiness(self):
        self.settings.metadata.write_text('tampered',encoding='utf-8')
        with TestClient(create_app(self.settings,registry_loader=lambda _:self.registry)) as client:
            self.assertEqual(client.get('/api/v1/health/ready').status_code,503)

    def test_artifact_failure_disables_readiness(self):
        def fail(_): raise ValueError('PRIVATE_SYNTHETIC_USER and private path')
        with TestClient(create_app(self.settings,registry_loader=fail)) as client:
            r=client.get('/api/v1/health/ready')
            self.assertEqual(r.status_code,503)
            self.assertNotIn('PRIVATE_SYNTHETIC_USER',r.text)

    def test_shutdown_releases_registry(self):
        app=create_app(self.settings,registry_loader=lambda _:self.registry)
        with TestClient(app): self.assertTrue(app.state.ready)
        self.assertFalse(app.state.ready)
        self.assertIsNone(app.state.registry)
