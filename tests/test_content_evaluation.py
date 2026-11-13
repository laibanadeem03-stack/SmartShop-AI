"""End-to-end synthetic temporal selection and unchanged control regression."""
import contextlib
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scipy import sparse
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import content_tfidf as content
import evaluate_content as pipeline
import evaluate_popularity as evaluation
import item_cf
import popularity_baseline as popularity
import prepare_evaluation as prep


def write_csv(path,rows):
    with path.open('x',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream,lineterminator='\n')
        writer.writerow(prep.HEADER)
        writer.writerows(rows)


def fixture(root):
    evaluation_dir, metadata_dir, cf_dir=(root/name for name in ('evaluation','metadata','cf'))
    for directory in (evaluation_dir,metadata_dir,cf_dir):
        directory.mkdir()
    train=[('u','A','5','50'),('v','B','4','50'),('w','C','1','50'),('x','D','3','50'),('u','E','2','50')]
    validation=[('u','B','5','150'),('cold','E','5','150'),('w','A','4','150'),('v','C','2','150')]
    test=[('v','A','5','250'),('cold','D','4','250'),('u','C','4','250'),('x','E','5','250')]
    partitions={}
    for name,rows in (('train',train),('validation',validation),('test',test)):
        path=evaluation_dir/(name+'.csv')
        write_csv(path,rows)
        partitions[name]={'path':str(path),'sha256':prep.sha256(path),'interactions':len(rows)}
    subset=root/'subset.csv'
    write_csv(subset,train+validation+test)
    manifest={'status':'complete','partitions':partitions,
              'protocol':{'train_end_inclusive_ms':100,'validation_end_inclusive_ms':200},
              'source':{'path':str(subset),'sha256':prep.sha256(subset)}}
    prep.write_json(evaluation_dir/'split_manifest.json',manifest)
    records=[{'parent_asin':key,'title':title,'main_category':'Phones','categories':['Cases']}
             for key,title in [('A','red phone case 7'),('B','blue phone case 7'),('C','tablet stand'),('D','---'),('E','usb charger')]]
    metadata_path=metadata_dir/'selected_metadata.jsonl'
    metadata_path.write_text(''.join(json.dumps(row)+'\n' for row in records),encoding='utf-8')
    prep.write_json(metadata_dir/'post_run_integrity.json',{
        'all_four_source_values_verified_against_sqlite_and_jsonl':True,'protected_sources_unchanged':True})
    prep.write_json(metadata_dir/'results_recovery.json',{'status':'complete','metadata_jsonl_sha256':prep.sha256(metadata_path)})
    snapshot=popularity.fit_training(train,100)
    positive,users,items=item_cf.positive_matrix(train,snapshot)
    graph=sparse.csr_array((len(items),len(items)),dtype=np.float32)
    item_cf.save_sparse(cf_dir/'positive_training.npz',positive)
    item_cf.save_sparse(cf_dir/'neighbors_item_cf_k50_lambda10.npz',graph)
    prep.write_json(cf_dir/'id_mappings.json',{'users':users,'products':items})
    rank=popularity.build_ranking(snapshot)
    seen=popularity.extend_history(snapshot['seen'],validation,200)
    prior={'training':{'fingerprint':popularity.fingerprint(snapshot)}}
    cf_prior={'selection':{'best_cf_configuration':'item_cf_k50_lambda10'}}
    for window,rows,mask,begin,end in (('validation',validation,snapshot['seen'],100,200),('test',test,seen,200,None)):
        prior[window]={'count':evaluation.evaluate_window(rows,rank,snapshot,mask,begin,end,
                          prediction_path=evaluation_dir/(window+'_predictions_count.csv'))}
        recommender=item_cf.ItemRecommender(positive,users,items,graph,snapshot)
        cf_prior[window]={'item_cf_k50_lambda10':evaluation.evaluate_window(rows,rank,snapshot,mask,begin,end,
                               prediction_path=cf_dir/(window+'_predictions_item_cf_k50_lambda10.csv'),recommender=recommender)}
    prep.write_json(evaluation_dir/'results.json',prior)
    prep.write_json(cf_dir/'results.json',cf_prior)
    return evaluation_dir,metadata_dir,cf_dir


class ContentEvaluationTests(unittest.TestCase):
    def test_exact_selection_ties_follow_predeclared_priority(self):
        results={pipeline.name_for(df,w):{'segments':{'overall':{'ndcg_at_10':.1}}}
                 for df,w in pipeline.CONFIGURATIONS}
        self.assertEqual(pipeline.select_configuration(results),'tfidf_df2_title80')
        results['tfidf_df1_title95']['segments']['overall']['ndcg_at_10']=.2
        self.assertEqual(pipeline.select_configuration(results),'tfidf_df1_title95')

    def test_content_callback_uses_existing_metrics_and_keeps_cold_targets(self):
        rows=[('u','A','5','50'),('v','B','4','50'),('w','C','1','50')]
        snapshot=popularity.fit_training(rows,100)
        positive,users,items=item_cf.positive_matrix(rows,snapshot)
        features=sparse.csr_matrix([[1,0],[1,0],[0,1]],dtype=np.float32)
        model=content.ContentRecommender(positive,users,items,features,snapshot)
        holdout=[('u','B','5','150'),('u','COLD','5','150')]
        result=evaluation.evaluate_window(holdout,popularity.build_ranking(snapshot),snapshot,snapshot['seen'],100,200,recommender=model)
        self.assertEqual(result['segments']['overall']['recall_at_10'],.5)
        self.assertEqual(result['segments']['warm_user_cold_product']['recall_at_10'],0)

    def test_pipeline_selection_precedes_test_reads_and_controls_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            source,metadata,cf=fixture(root)
            original_sha=prep.sha256
            original_read=Path.read_text
            test_path=source/'test.csv'
            def check_selection():
                self.assertTrue(list(root.glob('content-tfidf-*/validation_selection.json')))
            def guarded_sha(path):
                if Path(path)==test_path:
                    check_selection()
                return original_sha(path)
            def guarded_read(path,*args,**kwargs):
                if path in (source/'results.json',cf/'results.json'):
                    check_selection()
                return original_read(path,*args,**kwargs)
            with patch.object(prep,'LOCAL',root),patch.object(prep,'sha256',side_effect=guarded_sha),patch.object(Path,'read_text',guarded_read),contextlib.redirect_stdout(io.StringIO()):
                result=pipeline.run(source,metadata,cf,root/'report.md',expected_catalog=None,expected_metadata=None)
            self.assertEqual(result['status'],'complete')
            self.assertTrue(all(value is True for key,value in result['integrity'].items() if key!='protected_files'))
            self.assertEqual(result['selection']['selected_content'],pipeline.select_configuration(result['validation']))
            self.assertEqual(result['training']['products'],5)
            self.assertFalse(result['selection']['test_used_for_selection'])
            directory=Path(result['run_directory'])
            import joblib
            loaded=joblib.load(directory/'vectorizers_df1.joblib')
            self.assertEqual(loaded['title'].transform(['unseenword']).nnz,0)
            with patch.object(prep,'LOCAL',root):
                recommender=content.load_artifacts(directory)
            self.assertEqual(recommender.items,sorted(recommender.snapshot['items']))
            self.assertEqual(recommender('cold',set(),1)[0][0],'A')
            saved=json.loads((directory/'training_snapshot.json').read_text())
            saved['training']['items']['A']['count']+=1
            (directory/'training_snapshot.json').write_text(json.dumps(saved),encoding='utf-8')
            with patch.object(prep,'LOCAL',root),self.assertRaises(ValueError):
                content.load_artifacts(directory)


if __name__=='__main__':
    unittest.main()
