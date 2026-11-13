"""Registration trust boundaries and fresh-run receipts; synthetic data only."""
from copy import deepcopy
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from backend.app.config import LOCAL, ROOT, Settings
if str(ROOT/'scripts') not in sys.path:
    sys.path.insert(0,str(ROOT/'scripts'))
from backend.app.artifact_provenance import build_registration, relative, sha256, verify_registration
from backend.app.services.model_registry import load_registry
from scripts.configure_serving import register
import evaluate_content


def write(path, value):
    path.write_text(json.dumps(value,sort_keys=True),encoding='utf-8')


def fixture(root):
    content, cf, hybrid = (root/name for name in ('content','cf','hybrid'))
    for directory in (content,cf,hybrid):
        directory.mkdir()
    metadata=root/'metadata.jsonl'
    metadata.write_text('{"parent_asin":"SYNTHETIC"}\n',encoding='utf-8')
    component=cf/'positive_training.npz';component.write_bytes(b'synthetic-not-a-real-model')
    fingerprints={'training':'1'*64,'positive':'2'*64,'content':'3'*64,'cf_graph':'4'*64}
    components={'cf_directory':str(cf),'content_directory':str(content),
        'cf_configuration':'item_cf_k50_lambda10','content_configuration':'tfidf_df2_title80',
        **{key+'_fingerprint':value for key,value in fingerprints.items()}}
    manifest={**components,'component_file_sha256':{str(component):sha256(component)},
        'default_model':'hybrid','rank_constant':60,'selected_cf_weight':.5,
        'scores_are_probabilities':False,'score_type':'normalized_weighted_rrf'}
    scores={'tfidf_df2_title80':.3,'hybrid_cf10':.4,'hybrid_cf25':.5,'hybrid_cf50':.6,'hybrid_cf75':.55}
    decision={'selected_hybrid':'hybrid_cf50','selected_cf_weight':.5,'default_model':'hybrid',
        'strict_validation_improvement':True,'test_used_for_selection':False,
        'best_hybrid_validation_ndcg':.6,'content_validation_ndcg':.3,
        'validation_ndcg':scores,'tie_priority':list(scores)[1:],
        'rank_constant':60,'frozen_component_fingerprints':fingerprints}
    def metric(value):return {'cohort':{'users_with_positive_holdout':2},
        'segments':{'overall':{'ndcg_at_10':value,'recall_at_10':value,'catalog_coverage_at_10':.5,'evaluated_users':2}},
        'predictions':{'sha256':'a'*64}}
    results={'status':'complete','components':components,'selection':decision,
        'run_directory':str(hybrid),'created_utc':'synthetic','resources':{'elapsed_seconds':1},
        'integrity':{key:True for key in ('source_files_unchanged','component_models_unchanged',
            'all_original_controls_identical','test_read_after_default_decision')}}
    results['integrity']['existing_models_retrained']=False
    for split in ('validation','test'):
        results[split]={'count':metric(.1),'item_cf_k50_lambda10':metric(.2),**{k:metric(v) for k,v in scores.items()}}
    for folder,name in ((cf,'item_cf_k50_lambda10'),(content,'tfidf_df2_title80')):
        write(folder/'results.json',{split:{name:results[split][name],'count':results[split]['count']} for split in ('validation','test')})
    write(hybrid/'results.json',results);write(hybrid/'hybrid_manifest.json',manifest);write(hybrid/'validation_selection.json',decision)
    return hybrid,metadata


class PublicationProvenanceTests(unittest.TestCase):
    def setUp(self):
        LOCAL.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='registration-test-',dir=LOCAL)
        self.root=Path(self.temp.name);self.hybrid,self.metadata=fixture(self.root)
        self.registration=build_registration(self.hybrid,self.metadata,sha256(self.metadata))

    def tearDown(self):self.temp.cleanup()

    def test_valid_rebuild_accepts_new_resources_and_result_bytes(self):
        first=self.registration['files'][relative(self.hybrid/'results.json')]
        result=json.loads((self.hybrid/'results.json').read_text());result['created_utc']='another-synthetic-run';result['resources']['elapsed_seconds']=200
        write(self.hybrid/'results.json',result)
        rebuilt=build_registration(self.hybrid,self.metadata,sha256(self.metadata))
        self.assertNotEqual(first,rebuilt['files'][relative(self.hybrid/'results.json')])
        self.assertEqual(verify_registration(rebuilt)[1]['selection'],result['selection'])

    def test_independent_fresh_run_has_its_own_valid_registration(self):
        another=self.root/'another-run';another.mkdir()
        hybrid,metadata=fixture(another)
        fresh=build_registration(hybrid,metadata,sha256(metadata))
        self.assertNotEqual(fresh['hybrid_directory'],self.registration['hybrid_directory'])
        self.assertNotEqual(fresh['hybrid_manifest_sha256'],self.registration['hybrid_manifest_sha256'])
        verify_registration(fresh)

    def test_native_array_fingerprints_are_still_required_after_registration(self):
        model=SimpleNamespace(cf_weight=.5,items=['synthetic'],snapshot={},
            cf=SimpleNamespace(matrix='positive',users=['u'],graph='graph'),
            content=SimpleNamespace(features='features'))
        settings=Settings.from_registration(self.registration,database=self.root/'unused',database_sha256='',expected_eligible=1)
        with patch('hybrid_ranker.load_artifacts',return_value=model), \
             patch('popularity_baseline.fingerprint',return_value='1'*64), \
             patch('item_cf.array_fingerprint',side_effect=['2'*64,'4'*64,'f'*64]):
            with self.assertRaisesRegex(ValueError,'fingerprints'):load_registry(settings)

    def test_pinned_result_tampering_fails_before_native_deserialization(self):
        result=json.loads((self.hybrid/'results.json').read_text());result['test']['hybrid_cf50']['segments']['overall']['ndcg_at_10']=.99
        write(self.hybrid/'results.json',result)
        settings=Settings.from_registration(self.registration,database=self.root/'unused',database_sha256='')
        with patch('hybrid_ranker.load_artifacts') as native:
            with self.assertRaises(ValueError):load_registry(settings)
            native.assert_not_called()

    def test_component_and_metadata_byte_tampering_rejected(self):
        for target in (self.metadata,self.root/'cf/positive_training.npz'):
            original=target.read_bytes();target.write_bytes(original+b'changed')
            with self.assertRaises(ValueError):verify_registration(self.registration)
            target.write_bytes(original)

    def test_omitted_input_and_outside_local_paths_rejected(self):
        reg=deepcopy(self.registration);reg['files'].pop(relative(self.hybrid/'results.json'))
        with self.assertRaises(ValueError):verify_registration(reg)
        reg=deepcopy(self.registration);reg['files']['../outside-local']='a'*64
        with self.assertRaises(ValueError):verify_registration(reg)

    def test_repinning_mismatched_component_or_control_does_not_validate_lineage(self):
        original=json.loads((self.hybrid/'results.json').read_text())
        for mutate in (lambda r:r['components'].update(training_fingerprint='f'*64),
                       lambda r:r['test']['item_cf_k50_lambda10']['segments']['overall'].update(ndcg_at_10=.99)):
            result=deepcopy(original);mutate(result);write(self.hybrid/'results.json',result)
            with self.assertRaises(ValueError):build_registration(self.hybrid,self.metadata,sha256(self.metadata))

    def test_modified_decision_and_gate_rejected_even_if_report_matches_it(self):
        result=json.loads((self.hybrid/'results.json').read_text());decision=result['selection'];decision['test_used_for_selection']=True
        write(self.hybrid/'results.json',result);write(self.hybrid/'validation_selection.json',decision)
        with self.assertRaises(ValueError):build_registration(self.hybrid,self.metadata,sha256(self.metadata))

    def test_relative_configuration_and_pointer_bindings(self):
        config=self.root/'serving.json';write(config,self.registration)
        database=self.root/'app.sqlite3';database.write_bytes(b'synthetic-db')
        pointer=self.root/'application.json'
        info={'database':relative(database),'database_sha256':sha256(database),
            'metadata_sha256':sha256(self.metadata),'model_manifest_sha256':self.registration['hybrid_manifest_sha256'],
            'serving_config':relative(config),'serving_config_sha256':sha256(config)}
        write(pointer,info)
        with patch.dict(os.environ,{'SMARTSHOP_APP_MANIFEST':str(pointer),'SMARTSHOP_SERVING_CONFIG':str(config)}):
            settings=Settings.from_environment();self.assertEqual(settings.hybrid_directory,self.hybrid)
            self.assertEqual(settings.database,database)
            info['model_manifest_sha256']='f'*64;write(pointer,info)
            with self.assertRaises(ValueError):Settings.from_environment()
            info['model_manifest_sha256']=self.registration['hybrid_manifest_sha256'];write(pointer,info)
            config.write_text(config.read_text()+'\n')
            with self.assertRaises(ValueError):Settings.from_environment()

    def test_registration_never_overwrites_configuration(self):
        path=self.root/'existing.json';path.write_text('keep')
        with self.assertRaises(FileExistsError):register(self.hybrid,self.metadata,sha256(self.metadata),path)
        self.assertEqual(path.read_text(),'keep')


class AcquisitionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'selected_metadata.jsonl').write_text('synthetic\n')
        self.result={'status':'complete','metadata_jsonl_sha256':sha256(self.root/'selected_metadata.jsonl')}
        write(self.root/'post_run_integrity.json',{'all_four_source_values_verified_against_sqlite_and_jsonl':True,'protected_sources_unchanged':True})

    def tearDown(self):self.temp.cleanup()

    def test_normal_success_and_recovery_success_supported(self):
        write(self.root/'results.json',self.result)
        self.assertEqual(evaluate_content.metadata_acquisition(self.root),self.result)
        write(self.root/'results_recovery.json',self.result)
        self.assertEqual(evaluate_content.metadata_acquisition(self.root),self.result)

    def test_failed_or_corrupt_recovery_does_not_fall_back_to_earlier_success(self):
        write(self.root/'results.json',self.result)
        for result in ({**self.result,'status':'stopped'},{**self.result,'metadata_jsonl_sha256':'f'*64}):
            write(self.root/'results_recovery.json',result)
            with self.assertRaises(ValueError):evaluate_content.metadata_acquisition(self.root)

    def test_new_verification_receipt_pins_exact_result(self):
        path=self.root/'results.json';write(path,self.result)
        write(self.root/'post_run_integrity.json',{'all_four_source_values_verified_against_sqlite_and_jsonl':True,
            'protected_sources_unchanged':True,'acquisition_result_file':path.name,'acquisition_result_sha256':sha256(path)})
        evaluate_content.metadata_acquisition(self.root)
        path.write_text(path.read_text()+'\n')
        with self.assertRaises(ValueError):evaluate_content.metadata_acquisition(self.root)
