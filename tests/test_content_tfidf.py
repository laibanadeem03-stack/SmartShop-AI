"""Synthetic text, vocabulary leakage, sparse scoring and fallback checks."""
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import content_tfidf as content
import item_cf
import popularity_baseline as popularity


def fixture():
    rows = [('u','A','4','50'), ('u2','B','2','50'), ('u3','C','5','50'),
            ('u4','D','1','50'), ('u5','E','3','50')]
    snapshot = popularity.fit_training(rows,100)
    positive,users,items = item_cf.positive_matrix(rows,snapshot)
    features = sparse.csr_matrix(np.array([[1,0],[.8,.6],[0,1],[0,0],[.8,.6]],dtype=np.float32))
    return snapshot,positive,users,items,features


def records():
    return {key:{'parent_asin':key,'title':title,'main_category':'Phones','categories':['Phones','Cases']}
            for key,title in [('A','USB-C PD 20W iPhone 7'),('B','iPhone 7 blue case'),
                              ('C','red tablet cover'),('FUTURE','futureexclusive token')]}


class TextFeaturesTests(unittest.TestCase):
    def test_cleaning_preserves_technical_words_numbers_and_negation(self):
        self.assertEqual(content.clean_text('<b>USB-C</b> PD 20W &amp; iPhone 7 NOT waterproof'),
                         'usb-c pd 20w & iphone 7 not waterproof')
        self.assertEqual(content.clean_text('PD < 20W > NOT waterproof'),'pd < 20w > not waterproof')
        for value in (None,'  ','N/A','&lt;br&gt;','---'):
            self.assertEqual(content.clean_text(value),'')
        with self.assertRaises(ValueError):
            content.clean_text(123)

    def test_categories_deduplicated_and_identifier_excluded(self):
        data=records()
        data['A']['categories']=[' phones ','Cases','Cases']
        titles,categories=content.documents(data,['A'])
        self.assertEqual(categories,['phones cases'])
        self.assertNotIn('parent_asin',titles[0])
        with self.assertRaises(ValueError):
            content.documents(data,['MISSING'])

    def test_training_only_vocabulary_idf_and_single_character_model_number(self):
        data=records()
        fields=content.fit_fields(data,['A','B','C'],1,max_df=1.0)
        vectorizer=fields['title_vectorizer']
        self.assertNotIn('futureexclusive',vectorizer.vocabulary_)
        self.assertIn('7',vectorizer.vocabulary_)
        self.assertIn('iphone 7',vectorizer.vocabulary_)
        self.assertAlmostEqual(float(vectorizer.idf_[vectorizer.vocabulary_['iphone']]),1+math.log(4/3),places=6)
        before=content.field_fingerprint(fields)
        data['FUTURE']['title']='iphone '*100+'leaktoken'
        after=content.fit_fields(data,['A','B','C'],1,max_df=1.0)
        self.assertEqual(before,content.field_fingerprint(after))
        transformed=vectorizer.transform(['unseenterm'])
        self.assertEqual(transformed.nnz,0)

    def test_float32_vocabulary_bounds_and_no_base_mutation(self):
        fields=content.fit_fields(records(),['A','B','C'],1,title_cap=4,category_cap=2,max_df=1.0)
        before=content.field_fingerprint(fields)
        for weight in (.8,.95):
            matrix=content.combine_fields(fields,weight)
            self.assertEqual(matrix.dtype,np.float32)
            self.assertLessEqual(matrix.shape[1],6)
            self.assertTrue(sparse.isspmatrix_csr(matrix))
            np.testing.assert_allclose(np.asarray(matrix.multiply(matrix).sum(axis=1)).ravel(),1,atol=1e-6)
        self.assertEqual(before,content.field_fingerprint(fields))

    def test_field_weighted_cosine_hand_calculation(self):
        fields={'title':sparse.csr_matrix([[1.,0],[1.,0]],dtype=np.float32),
                'category':sparse.csr_matrix([[1.,0],[0.,1]],dtype=np.float32)}
        matrix=content.combine_fields(fields,.8)
        self.assertAlmostEqual(float((matrix[0:1]@matrix[1:2].T)[0,0]),.8,places=6)

    def test_empty_vocabularies_are_zero_sparse_rows(self):
        data={key:{'title':'---','main_category':None,'categories':[]} for key in ('A','B')}
        fields=content.fit_fields(data,['A','B'],2)
        matrix=content.combine_fields(fields,.8)
        self.assertEqual(matrix.shape,(2,0))
        self.assertEqual(matrix.nnz,0)
        self.assertIsNone(fields['title_vectorizer'])

    def test_metadata_schema_checksum_identity_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'metadata.jsonl'
            data={'parent_asin':'0000000001','title':'Original &amp; text','main_category':None,'categories':[]}
            path.write_text(json.dumps(data)+'\n',encoding='utf-8')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            loaded=content.load_metadata(path,digest)
            self.assertEqual(loaded['0000000001'],data)
            with self.assertRaises(ValueError):
                content.load_metadata(path,'0'*64)
            path.write_text((json.dumps(data)+'\n')*2,encoding='utf-8')
            with self.assertRaises(ValueError):
                content.load_metadata(path,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_feature_rows_follow_ids_not_metadata_insertion_order(self):
        data=records()
        a=content.fit_fields(data,['C','A','B'],1,max_df=1.0)
        b=content.fit_fields(dict(reversed(list(data.items()))),['C','A','B'],1,max_df=1.0)
        self.assertEqual(content.field_fingerprint(a),content.field_fingerprint(b))
        self.assertEqual(a['items'],['C','A','B'])


class RecommendationTests(unittest.TestCase):
    def test_profile_is_normalized_sum_and_four_five_stars_are_equal(self):
        _,_,_,_,features=fixture()
        profiles=[]
        for first,second in (('4','5'),('5','4')):
            rows=[('u','A',first,'50'),('u','C',second,'50'),('v','B','1','50'),
                  ('w','D','2','50'),('x','E','3','50')]
            snapshot=popularity.fit_training(rows,100)
            positive,users,items=item_cf.positive_matrix(rows,snapshot)
            model=content.ContentRecommender(positive,users,items,features,snapshot)
            profile=model.profile('u')
            profiles.append(profile.data.copy())
            np.testing.assert_allclose(profile.data,[1/math.sqrt(2)]*2,atol=1e-6)
            recommendation=model('u',{'A','C'},1)[0]
            self.assertEqual(recommendation[0],'B')
            self.assertAlmostEqual(recommendation[1],1.4/math.sqrt(2),places=6)
        np.testing.assert_array_equal(*profiles)

    def test_personalized_cosine_deterministic_ties_exclusions_and_backfill(self):
        snapshot,positive,users,items,features=fixture()
        model=content.ContentRecommender(positive,users,items,features,snapshot)
        result=model('u',{'A'},4)
        self.assertEqual([p for p,_ in result],['B','E','C','D'])
        self.assertAlmostEqual(result[0][1],.8,places=6)
        self.assertEqual(model.last_sources,['content','content','popularity_fallback','popularity_fallback'])
        self.assertEqual(model('u',{'A'},4),result)
        self.assertEqual([p for p,_ in model('u',{'A','B'},2)],['E','C'])

    def test_cold_negative_only_and_zero_feature_profiles_fall_back(self):
        snapshot,positive,users,items,features=fixture()
        model=content.ContentRecommender(positive,users,items,features,snapshot)
        for user in ('cold','u2','u4','u5'):
            result=model(user,set(),3)
            self.assertEqual([p for p,_ in result],['A','B','C'])
            self.assertEqual(model.last_sources,['popularity_fallback']*3)
        zero=content.ContentRecommender(positive,users,items,sparse.csr_matrix((5,0),dtype=np.float32),snapshot)
        self.assertEqual(zero('u',{'A'},1),[('B',0.0)])

    def test_training_profiles_and_models_frozen_when_seen_masks_change(self):
        snapshot,positive,users,items,features=fixture()
        model=content.ContentRecommender(positive,users,items,features,snapshot)
        before=(popularity.fingerprint(snapshot),item_cf.array_fingerprint(positive),item_cf.array_fingerprint(features))
        masks=popularity.extend_history(snapshot['seen'],[('cold','B','5','150'),('u','E','5','160')],200)
        self.assertEqual(model.profile('cold').nnz,0)
        self.assertEqual([p for p,_ in model('cold',masks['cold'],2)],['A','C'])
        model('u',masks['u'],3)
        self.assertEqual(before,(popularity.fingerprint(snapshot),item_cf.array_fingerprint(positive),item_cf.array_fingerprint(features)))

    def test_no_dense_conversion_and_only_one_query_score_column(self):
        snapshot,positive,users,items,features=fixture()
        model=content.ContentRecommender(positive,users,items,features,snapshot)
        with patch.object(sparse.csr_matrix,'toarray',side_effect=AssertionError('Dense forbidden')),patch.object(sparse.csr_matrix,'todense',side_effect=AssertionError('Dense forbidden')):
            self.assertEqual(model.similar_items('A',2)[0][0],'B')
            self.assertEqual(model('u',{'A'},2)[0][0],'B')

    def test_positive_training_builder_rejects_future_rows(self):
        snapshot,_,_,_,_=fixture()
        with self.assertRaises(ValueError):
            item_cf.positive_matrix([('u','A','5','101')],snapshot)

    def test_alignment_and_dtype_fail_closed(self):
        snapshot,positive,users,items,features=fixture()
        for bad_users,bad_items,bad_features in ((users[::-1],items,features),(users,items[::-1],features),(users,items,features.astype(np.float64))):
            with self.assertRaises(ValueError):
                content.ContentRecommender(positive,bad_users,bad_items,bad_features,snapshot)


if __name__=='__main__':
    unittest.main()
