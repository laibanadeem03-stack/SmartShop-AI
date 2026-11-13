"""Strict default gate, cache boundaries and frozen-component integration."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scipy import sparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import content_tfidf as content
import evaluate_content
import evaluate_hybrid as pipeline
import hybrid_ranker as hybrid
import item_cf
import popularity_baseline as popularity
import prepare_evaluation as prep
from test_content_evaluation import fixture as content_fixture


def metric(value):
    return {'segments':{'overall':{'ndcg_at_10':value}}}


class GateTests(unittest.TestCase):
    def test_equal_or_worse_retains_content_and_lowest_cf_weight_wins_tie(self):
        results={'content':metric(.1),**{hybrid.name_for(w):metric(.1) for w in hybrid.CF_WEIGHTS}}
        decision=pipeline.decide_default(results,'content')
        self.assertEqual(decision['default_model'],'content')
        self.assertEqual(decision['selected_cf_weight'],.1)
        results['content']=metric(.2)
        self.assertEqual(pipeline.decide_default(results,'content')['default_model'],'content')

    def test_strict_full_precision_improvement_enables_hybrid(self):
        results={'content':metric(.1),**{hybrid.name_for(w):metric(.1) for w in hybrid.CF_WEIGHTS}}
        results['hybrid_cf25']=metric(.1+1e-12)
        decision=pipeline.decide_default(results,'content')
        self.assertEqual(decision['default_model'],'hybrid')
        self.assertTrue(decision['strict_validation_improvement'])
        self.assertEqual(decision['selected_cf_weight'],.25)

    def test_undefined_or_nonfinite_metric_rejected(self):
        for value in (None,float('nan'),float('inf')):
            results={'content':metric(value),**{hybrid.name_for(w):metric(.1) for w in hybrid.CF_WEIGHTS}}
            with self.assertRaises(ValueError):
                pipeline.decide_default(results,'content')

    def test_prediction_cache_rejects_different_history(self):
        callback=pipeline.CachedPredictions({'u':([('A',.5)],['hybrid_both'])},{'u':frozenset({'B'})})
        self.assertEqual(callback('u',{'B'}),[('A',.5)])
        with self.assertRaises(ValueError):
            callback('u',{'C'})


class PipelineTests(unittest.TestCase):
    def test_frozen_models_no_retraining_selection_precedes_test_and_all_controls_reproduce(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            source,metadata,cf=content_fixture(root)
            cf_prior=json.loads((cf/'results.json').read_text())
            cf_prior['source_split_manifest_sha256']=prep.sha256(source/'split_manifest.json')
            (cf/'results.json').write_text(json.dumps(cf_prior),encoding='utf-8')
            with patch.object(prep,'LOCAL',root),contextlib.redirect_stdout(io.StringIO()):
                content_result=evaluate_content.run(source,metadata,cf,root/'content.md',expected_catalog=None,expected_metadata=None)
            cb=Path(content_result['run_directory'])
            saved=json.loads((cb/'training_snapshot.json').read_text())
            mapping=json.loads((cb/'id_mappings.json').read_text())
            positive=sparse.load_npz(cf/'positive_training.npz')
            graph=sparse.load_npz(cf/'neighbors_item_cf_k50_lambda10.npz')
            prep.write_json(cf/'validation_selection.json',{
                'best_cf_configuration':'item_cf_k50_lambda10','frozen_training_fingerprint':saved['fingerprint'],
                'frozen_positive_matrix_fingerprint':item_cf.array_fingerprint(positive,mapping['users'],mapping['products']),
                'selected_graph_fingerprint':item_cf.array_fingerprint(graph)})
            before={path:prep.sha256(path) for directory in (source,cf,cb) for path in directory.rglob('*') if path.is_file()}
            original_sha=prep.sha256
            original_read=Path.read_text
            def selected():
                files=list(root.glob('hybrid-*/validation_selection.json'))
                self.assertEqual(len(files),1)
                decision=json.loads(original_read(files[0]))
                self.assertEqual(decision['default_model'],'content')
                self.assertFalse(decision['test_used_for_selection'])
            def guarded_sha(path):
                if Path(path)==source/'test.csv':
                    selected()
                return original_sha(path)
            def guarded_read(path,*args,**kwargs):
                if path in (source/'results.json',cf/'results.json',cb/'results.json'):
                    selected()
                return original_read(path,*args,**kwargs)
            with patch.object(prep,'LOCAL',root),patch.object(prep,'sha256',side_effect=guarded_sha), \
                 patch.object(Path,'read_text',guarded_read), \
                 patch.object(content,'fit_fields',side_effect=AssertionError('Content retrain forbidden')), \
                 patch.object(item_cf,'positive_matrix',side_effect=AssertionError('Profile retrain forbidden')), \
                 patch.object(popularity,'fit_training',side_effect=AssertionError('Count retrain forbidden')), \
                 contextlib.redirect_stdout(io.StringIO()):
                result=pipeline.run(source,cb,cf,root/'hybrid.md',expected_catalog=None,expected_content=None)
            self.assertEqual(result['selection']['default_model'],'content')
            self.assertTrue(result['integrity']['all_original_controls_identical'])
            self.assertFalse(result['integrity']['existing_models_retrained'])
            self.assertTrue(all(prep.sha256(path)==digest for path,digest in before.items()))
            directory=Path(result['run_directory'])
            with patch.object(prep,'LOCAL',root):
                default=hybrid.load_artifacts(directory,expected_catalog=None,expected_content=None)
                challenger=hybrid.load_artifacts(directory,challenger=True,expected_catalog=None,expected_content=None)
            self.assertIsInstance(default,content.ContentRecommender)
            self.assertIsInstance(challenger,hybrid.HybridRecommender)
            self.assertEqual(challenger.cf_weight,.1)
            manifest_path=directory/'hybrid_manifest.json'
            saved_manifest=manifest_path.read_text(encoding='utf-8')
            changed=json.loads(saved_manifest)
            changed['default_model']='hybrid'
            manifest_path.write_text(json.dumps(changed),encoding='utf-8')
            with patch.object(prep,'LOCAL',root),self.assertRaises(ValueError):
                hybrid.load_artifacts(directory,expected_catalog=None,expected_content=None)
            manifest_path.write_text(saved_manifest,encoding='utf-8')
            # Hash protection rejects changed referenced models, in fixtures only.
            with (cb/'training_snapshot.json').open('a',encoding='utf-8') as stream:
                stream.write(' ')
            with patch.object(prep,'LOCAL',root),self.assertRaises(ValueError):
                hybrid.load_artifacts(directory,expected_catalog=None,expected_content=None)


if __name__=='__main__':
    unittest.main()
