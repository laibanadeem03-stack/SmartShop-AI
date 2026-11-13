"""Synthetic RRF arithmetic, fallback isolation, frozen signals and evidence."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import content_tfidf as content
import hybrid_ranker as hybrid
import item_cf
import popularity_baseline as popularity
from test_content_tfidf import fixture as content_fixture


def fixture(weight=.5,zero_content=False,zero_cf=False):
    snapshot,positive,users,items,features=content_fixture()
    graph=sparse.csr_array((np.asarray([.2,.1,.3],dtype=np.float32),([0,0,2],[1,2,4])),shape=(5,5))
    if zero_cf:
        graph=sparse.csr_array((5,5),dtype=np.float32)
    if zero_content:
        features=sparse.csr_matrix((5,0),dtype=np.float32)
    cf=item_cf.ItemRecommender(positive,users,items,graph,snapshot)
    cb=content.ContentRecommender(positive,users,items,features,snapshot)
    return hybrid.HybridRecommender(cf,cb,weight)


class FusionTests(unittest.TestCase):
    def test_hand_computed_agreement_and_no_per_item_renormalization(self):
        model=fixture()
        state=model.prepare_scores({'A':4,'C':1},{'B':.9,'C':.8},set())
        result=model.recommend_prepared(state,set(),5)
        self.assertEqual([p for p,_ in result],['C','A','B','D','E'])
        self.assertAlmostEqual(result[0][1],61/62)
        self.assertEqual(result[1][1],.5)
        self.assertEqual(result[2][1],.5)
        self.assertEqual(model.last_sources,['hybrid_both','cf_only','content_only','popularity_fallback','popularity_fallback'])
        for row in model.last_evidence:
            self.assertAlmostEqual(row['score'],row['cf_rank_contribution']+row['content_rank_contribution'])

    def test_single_available_signal_gets_full_weight(self):
        for weight in hybrid.CF_WEIGHTS:
            model=fixture(weight)
            for cf,cb,source in (({'B':1},{},'cf_only'),({}, {'B':1},'content_only')):
                state=model.prepare_scores(cf,cb,set())
                result=model.recommend_prepared(state,set(),1)
                self.assertEqual(result,[('B',1.0)])
                self.assertEqual(model.last_sources,[source])
                self.assertEqual(sum(model.effective_weights(state)),1)

    def test_availability_is_computed_after_seen_exclusions(self):
        model=fixture(.1)
        state=model.prepare_scores({'B':1},{'A':1},{'A'})
        self.assertEqual(model.effective_weights(state),(1,0))
        self.assertEqual(model.recommend_prepared(state,{'A'},1),[('B',1.)])

    def test_no_signal_popularity_once_and_no_duplicates(self):
        model=fixture()
        state=model.prepare_scores({}, {}, {'A'})
        result=model.recommend_prepared(state,{'A'},10)
        self.assertEqual([p for p,_ in result],['B','C','D','E'])
        self.assertEqual(model.last_sources,['popularity_fallback']*4)
        self.assertEqual(model.usage_summary()['fraction_fallback_slots'],1)
        self.assertEqual(model.usage_summary()['fraction_users_personalized'],0)
        self.assertEqual(model.effective_weights(state),(0,0))

    def test_component_backfilled_wrappers_are_never_called(self):
        model=fixture()
        with patch.object(item_cf.ItemRecommender,'__call__',side_effect=AssertionError('Backfill contamination')), \
             patch.object(content.ContentRecommender,'__call__',side_effect=AssertionError('Backfill contamination')):
            result=model('u',{'A'},5)
        self.assertEqual(result[0][0],'B')
        self.assertEqual(model.cf.usage,{})
        self.assertEqual(model.content.usage,{})

    def test_magnitude_scaling_does_not_change_ranks_or_scores(self):
        model=fixture(.25)
        states=[model.prepare_scores(cf,cb,set()) for cf,cb in (
            ({'A':4,'C':1},{'B':.9,'C':.8}),
            ({'A':4e9,'C':1e9},{'B':.9e-8,'C':.8e-8}))]
        self.assertEqual(model.recommend_prepared(states[0],set()),model.recommend_prepared(states[1],set()))

    def test_deterministic_ties_ignore_dictionary_order(self):
        model=fixture()
        first=model.prepare_scores({'B':1,'A':1},{'D':2,'C':2},set())
        second=model.prepare_scores({'A':1,'B':1},{'C':2,'D':2},set())
        self.assertEqual(model.recommend_prepared(first,set()),model.recommend_prepared(second,set()))
        self.assertEqual(first.cf_ranks[model.index['A']],1)

    def test_invalid_configuration_unknown_products_and_nonfinite_scores(self):
        for value in (0,1,.2,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                fixture(value)
        model=fixture()
        for scores in ({'OUTSIDE':1},{'A':float('nan')},{'A':float('inf')}):
            with self.assertRaises(ValueError):
                model.prepare_scores(scores,{},set())
        state=model.prepare_scores({'A':0,'B':-1},{},set())
        self.assertEqual(model.effective_weights(state),(0,0))

    def test_mask_changes_require_new_ranks_and_k_must_be_positive(self):
        model=fixture()
        state=model.prepare('u',{'A'})
        with self.assertRaises(ValueError):
            model.recommend_prepared(state,{'A','B'})
        with self.assertRaises(ValueError):
            model.recommend_prepared(state,{'A'},0)


class SignalEvidenceTests(unittest.TestCase):
    def test_cold_negative_only_zero_content_and_zero_cf(self):
        model=fixture()
        for user in ('cold','u2','u4','u5'):
            self.assertEqual(model(user,set(),2),[('A',0.),('B',0.)])
        cf_only=fixture(.1,zero_content=True)
        cf_only('u',{'A'},1)
        self.assertEqual(cf_only.last_sources,['cf_only'])
        self.assertEqual(cf_only.last_evidence[0]['effective_cf_weight'],1)
        cb_only=fixture(.75,zero_cf=True)
        cb_only('u',{'A'},1)
        self.assertEqual(cb_only.last_sources,['content_only'])

    def test_no_dense_conversion_and_no_future_profile_update(self):
        model=fixture()
        before=(popularity.fingerprint(model.snapshot),item_cf.array_fingerprint(model.cf.graph),
                item_cf.array_fingerprint(model.content.features),item_cf.array_fingerprint(model.content.positive))
        seen=popularity.extend_history(model.snapshot['seen'],[('cold','B','5','150'),('u','E','5','150')],200)
        with patch.object(sparse.csr_matrix,'toarray',side_effect=AssertionError('Dense forbidden')), \
             patch.object(sparse.csr_matrix,'todense',side_effect=AssertionError('Dense forbidden')):
            self.assertEqual(model('cold',seen['cold'],1),[('A',0.)])
            model('u',seen['u'])
        self.assertEqual(before,(popularity.fingerprint(model.snapshot),item_cf.array_fingerprint(model.cf.graph),
                item_cf.array_fingerprint(model.content.features),item_cf.array_fingerprint(model.content.positive)))

    def test_reason_support_reproduces_raw_component_scores(self):
        model=fixture()
        model.feature_names=[('title','technical_token'),('category','category_token')]
        model('u',{'A'},4)
        by_product={row['parent_asin']:row for row in model.last_evidence}
        both=model.explain('u',by_product['B'])
        self.assertAlmostEqual(both['cf_support']['total_seed_similarity'],both['raw_cf_score'])
        self.assertAlmostEqual(both['content_support']['total_feature_contribution'],both['raw_content_score'])
        self.assertEqual(both['cf_support']['seed_contributions'][0]['seed_product'],'A')
        cf_only=model.explain('u',by_product['C'])
        self.assertNotIn('content_support',cf_only)
        cb_only=model.explain('u',by_product['E'])
        self.assertNotIn('cf_support',cb_only)
        fallback=model.explain('u',by_product['D'])
        self.assertEqual(fallback['fallback_evidence'],'training_rating_interaction_count')
        self.assertNotIn('cf_support',fallback)
        self.assertNotIn('content_support',fallback)

    def test_stale_user_and_fabricated_contribution_evidence_rejected(self):
        model=fixture()
        model.feature_names=[('title','one'),('category','two')]
        model('u',{'A'},1)
        trace=model.last_evidence[0]
        with self.assertRaises(ValueError):
            model.explain('u2',trace)
        changed={**trace,'cf_rank_contribution':.123}
        with self.assertRaises(ValueError):
            model.explain('u',changed)


if __name__=='__main__':
    unittest.main()
