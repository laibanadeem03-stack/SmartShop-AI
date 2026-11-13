"""Frozen CF/content weighted RRF. Count backfill occurs only after fusion."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time

import numpy as np
from scipy import sparse

import content_tfidf as content
import item_cf
import popularity_baseline as popularity
import prepare_evaluation as prep

RANK_CONSTANT = 60
CF_WEIGHTS = (0.10, 0.25, 0.50, 0.75)


def name_for(weight):
    return f'hybrid_cf{round(weight*100):02d}'


def load_components(content_directory, cf_directory, expected_catalog=11012,
                    expected_content='tfidf_df2_title80'):
    """Load model state and validation selections, never prior test results."""
    content_directory = prep.require_local(content_directory)
    cf_directory = prep.require_local(cf_directory)
    selection = json.loads((content_directory/'validation_selection.json').read_text(encoding='utf-8'))
    cf_selection = json.loads((cf_directory/'validation_selection.json').read_text(encoding='utf-8'))
    selected = selection['selected_content']
    cf_name = cf_selection['best_cf_configuration']
    if ((expected_content is not None and selected != expected_content)
            or cf_name != 'item_cf_k50_lambda10'):
        raise ValueError('Frozen component configuration differs from approval')
    saved = json.loads((content_directory/'training_snapshot.json').read_text(encoding='utf-8'))
    snapshot = saved['training']
    snapshot['seen'] = {u:set(items) for u,items in snapshot['seen'].items()}
    mapping = json.loads((content_directory/'id_mappings.json').read_text(encoding='utf-8'))
    cf_mapping = json.loads((cf_directory/'id_mappings.json').read_text(encoding='utf-8'))
    users,items = mapping['users'],mapping['products']
    positive = sparse.load_npz(content_directory/'positive_training.npz')
    cf_positive = sparse.load_npz(cf_directory/'positive_training.npz')
    features = sparse.load_npz(content_directory/f'features_{selected}.npz')
    graph = sparse.load_npz(cf_directory/f'neighbors_{cf_name}.npz')
    training_hash = popularity.fingerprint(snapshot)
    positive_hash = item_cf.array_fingerprint(positive,users,items)
    if (mapping != cf_mapping or (expected_catalog is not None and len(items) != expected_catalog)
            or training_hash != saved['fingerprint']
            or training_hash != selection['training_fingerprint']
            or training_hash != cf_selection['frozen_training_fingerprint']
            or positive_hash != selection['positive_fingerprint']
            or positive_hash != cf_selection['frozen_positive_matrix_fingerprint']
            or positive_hash != item_cf.array_fingerprint(cf_positive,users,items)
            or item_cf.array_fingerprint(features,items=items) != selection['selected_model_fingerprint']
            or item_cf.array_fingerprint(graph) != cf_selection['selected_graph_fingerprint']):
        raise ValueError('Component fingerprints or ID mappings disagree')
    # Share one binary seed matrix; no CF graph or TF-IDF refit occurs.
    cb = content.ContentRecommender(positive,users,items,features,snapshot)
    cf = item_cf.ItemRecommender(positive,users,items,graph,snapshot)
    provenance = {'content_directory':str(content_directory),'cf_directory':str(cf_directory),
                  'content_configuration':selected,'cf_configuration':cf_name,
                  'training_fingerprint':training_hash,'positive_fingerprint':positive_hash,
                  'content_fingerprint':selection['selected_model_fingerprint'],
                  'cf_graph_fingerprint':cf_selection['selected_graph_fingerprint']}
    return cf,cb,provenance


@dataclass
class Signals:
    cf_scores: dict
    content_scores: dict
    cf_ranks: np.ndarray
    content_ranks: np.ndarray
    seen: frozenset
    profile: object = None
    user: object = None


class HybridRecommender:
    def __init__(self, cf_model, content_model, cf_weight):
        if not math.isfinite(cf_weight) or cf_weight not in CF_WEIGHTS:
            raise ValueError('CF weight must be one of the four approved values')
        if (cf_model.users != content_model.users or cf_model.items != content_model.items
                or popularity.fingerprint(cf_model.snapshot) != popularity.fingerprint(content_model.snapshot)):
            raise ValueError('CF/content catalog or training history mismatch')
        self.cf, self.content, self.cf_weight = cf_model,content_model,float(cf_weight)
        self.snapshot = content_model.snapshot
        self.items = content_model.items
        self.index = {item:i for i,item in enumerate(self.items)}
        self.counts = content_model.counts
        self.fallback = content_model.fallback
        self.usage = Counter()
        self.last_sources = []
        self.last_evidence = []
        self.last_signals = None
        self.latencies_ns = []
        self.feature_names = None

    def _rank(self, scores, seen):
        cleaned = {}
        for product,score in scores.items():
            if product not in self.index or not math.isfinite(float(score)):
                raise ValueError('Invalid component product or score')
            if score > 0 and product not in seen:
                cleaned[product] = float(score)
        ranks = np.zeros(len(self.items),dtype=np.int32)
        ordered = sorted(cleaned,key=lambda product:(-cleaned[product],-self.snapshot['items'][product]['count'],product))
        for rank,product in enumerate(ordered,1):
            ranks[self.index[product]] = rank
        return cleaned,ranks

    def prepare_scores(self, cf_scores, content_scores, seen, profile=None, user=None):
        cf,cr = self._rank(cf_scores,seen)
        cb,br = self._rank(content_scores,seen)
        return Signals(cf,cb,cr,br,frozenset(seen),profile,user)

    def prepare(self, user, seen):
        # Do not call either component's popularity-backfilled __call__ method.
        cf_scores = self.cf.score_candidates(user,seen)
        profile = self.content.profile(user)
        cb_scores = {}
        if profile.nnz:
            column = (self.content.features @ profile.T).tocoo()
            if column.shape != (len(self.items),1):
                raise ValueError('Only one sparse catalog score column is allowed')
            cb_scores = {self.items[int(row)]:float(value) for row,value in zip(column.row,column.data)}
        return self.prepare_scores(cf_scores,cb_scores,seen,profile,user)

    def effective_weights(self, signals):
        cf = self.cf_weight if signals.cf_scores else 0.0
        cb = 1-self.cf_weight if signals.content_scores else 0.0
        total = cf+cb
        return (cf/total,cb/total) if total else (0.0,0.0)

    def _trace(self, product, signals, weights, score):
        index = self.index[product]
        cr,br = int(signals.cf_ranks[index]),int(signals.content_ranks[index])
        cf_part = weights[0]*61/(RANK_CONSTANT+cr) if cr else 0.0
        cb_part = weights[1]*61/(RANK_CONSTANT+br) if br else 0.0
        source = ('hybrid_both' if cf_part and cb_part else 'cf_only' if cf_part
                  else 'content_only' if cb_part else 'popularity_fallback')
        return {'parent_asin':product,'score':float(score),'score_type':'normalized_weighted_rrf',
                'source':source,'cf_rank':cr or None,'content_rank':br or None,
                'raw_cf_score':signals.cf_scores.get(product),'raw_content_score':signals.content_scores.get(product),
                'configured_cf_weight':self.cf_weight,'effective_cf_weight':weights[0],
                'effective_content_weight':weights[1],'cf_rank_contribution':cf_part,
                'content_rank_contribution':cb_part,'training_interaction_count':int(self.counts[index])}

    def recommend_prepared(self, signals, seen, k=10):
        if k < 1 or signals.seen != frozenset(seen):
            raise ValueError('Invalid k or changed window exclusion mask')
        weights = self.effective_weights(signals)
        scores = np.zeros(len(self.items),dtype=np.float64)
        for weight,ranks in zip(weights,(signals.cf_ranks,signals.content_ranks)):
            active = ranks > 0
            scores[active] += weight*61/(RANK_CONSTANT+ranks[active].astype(np.float64))
        indices = np.flatnonzero(scores>0)
        order = np.lexsort((indices,-self.counts[indices],-scores[indices]))
        result = [(self.items[int(i)],float(scores[i])) for i in indices[order[:k]]]
        personalized = len(result)
        chosen = {item for item,_ in result}
        if len(result)<k:
            for product,_ in self.fallback:
                if product not in seen and product not in chosen:
                    result.append((product,0.0))
                    chosen.add(product)
                    if len(result)==k:
                        break
        self.last_evidence = [self._trace(product,signals,weights,score) for product,score in result]
        self.last_sources = [row['source'] for row in self.last_evidence]
        self.last_signals = signals
        self.usage['users'] += 1
        self.usage['users_with_personalized_recommendations'] += personalized>0
        self.usage['users_with_only_fallback'] += personalized==0
        self.usage['personalized_slots'] += personalized
        self.usage['fallback_slots'] += len(result)-personalized
        self.usage['total_slots'] += len(result)
        self.usage.update(self.last_sources)
        mode = ('both_signals' if all(weights) else 'cf_only' if weights[0]
                else 'content_only' if weights[1] else 'no_signals')
        self.usage['users_'+mode] += 1
        return result

    def __call__(self,user,seen,k=10):
        started = time.perf_counter_ns()
        result = self.recommend_prepared(self.prepare(user,seen),seen,k)
        self.latencies_ns.append(time.perf_counter_ns()-started)
        return result

    def usage_summary(self):
        c = self.usage
        return {**dict(c),'fraction_users_personalized':c['users_with_personalized_recommendations']/c['users'] if c['users'] else 0,
                'fraction_fallback_slots':c['fallback_slots']/c['total_slots'] if c['total_slots'] else 0}

    def load_feature_names(self, content_directory, selected_content):
        """Verify frozen vectorizers for evidence; never fit or transform text."""
        import joblib
        directory = prep.require_local(content_directory)
        selection = json.loads((directory/'validation_selection.json').read_text(encoding='utf-8'))
        df = int(selected_content.split('_')[1][2:])
        pair = joblib.load(directory/f'vectorizers_df{df}.joblib')
        fields = {}
        names = []
        for field in ('title','category'):
            vectorizer = pair[field]
            fields[field+'_vectorizer'] = vectorizer
            fields[field] = sparse.load_npz(directory/f'{field}_df{df}.npz')
            if vectorizer is not None:
                names.extend((field,str(term)) for term in vectorizer.get_feature_names_out())
        if (content.field_fingerprint(fields) != selection['field_fingerprints'][str(df)]
                or len(names) != self.content.features.shape[1]):
            raise ValueError('Evidence feature mapping does not match saved model')
        self.feature_names = names

    def explain(self,user,trace,signals=None,limit=3):
        """Exact component support; seed IDs/terms belong only in ignored outputs."""
        signals = signals if signals is not None else self.last_signals
        if signals is None or limit<1:
            raise ValueError('Expected recommendation signals and positive evidence limit')
        product = trace['parent_asin']
        if (signals.user is not None and signals.user != user) or product in signals.seen:
            raise ValueError('Evidence belongs to a different user or exclusion mask')
        expected = self._trace(product,signals,self.effective_weights(signals),trace['score'])
        if (trace != expected or not math.isclose(trace['score'],expected['cf_rank_contribution']+
                expected['content_rank_contribution'],rel_tol=1e-12,abs_tol=1e-14)):
            raise ValueError('Fusion evidence disagrees with the component signals')
        result = dict(trace)
        if trace['cf_rank_contribution']>0:
            row = self.cf.user_index.get(user)
            contributions = []
            if row is not None:
                start,stop = self.cf.matrix.indptr[row:row+2]
                target = self.index[product]
                for seed in self.cf.matrix.indices[start:stop]:
                    a,b = self.cf.graph.indptr[seed:seed+2]
                    for neighbor,value in zip(self.cf.graph.indices[a:b],self.cf.graph.data[a:b]):
                        if neighbor==target:
                            contributions.append({'seed_product':self.items[int(seed)],'similarity':float(value)})
            contributions.sort(key=lambda value:(-value['similarity'],value['seed_product']))
            result['cf_support'] = {'seed_contributions':contributions[:limit],
                                    'total_seed_similarity':sum(x['similarity'] for x in contributions)}
            if not math.isclose(result['cf_support']['total_seed_similarity'],trace['raw_cf_score'],rel_tol=1e-12,abs_tol=1e-12):
                raise ValueError('CF seed evidence does not reproduce the raw score')
        if trace['content_rank_contribution']>0:
            if self.feature_names is None or signals.profile is None:
                raise ValueError('Verified feature names/profile are required for term evidence')
            row = self.content.features[self.index[product]:self.index[product]+1]
            contributions = row.multiply(signals.profile).tocoo()
            order = np.lexsort((contributions.col,-contributions.data))
            result['content_support'] = {'top_shared_features':[
                {'field':self.feature_names[int(contributions.col[j])][0],
                 'term':self.feature_names[int(contributions.col[j])][1],
                 'dot_product_contribution':float(contributions.data[j])}
                for j in order[:limit]],
                'total_feature_contribution':float(np.sum(contributions.data,dtype=np.float64))}
            if not math.isclose(result['content_support']['total_feature_contribution'],trace['raw_content_score'],rel_tol=1e-6,abs_tol=1e-6):
                raise ValueError('Shared text evidence does not reproduce content cosine')
        if trace['source']=='popularity_fallback':
            result['fallback_evidence'] = 'training_rating_interaction_count'
        return result


def load_artifacts(directory, challenger=False, expected_catalog=11012, expected_content='tfidf_df2_title80'):
    directory = prep.require_local(directory)
    manifest = json.loads((directory/'hybrid_manifest.json').read_text(encoding='utf-8'))
    decision = json.loads((directory/'validation_selection.json').read_text(encoding='utf-8'))
    strict = decision['best_hybrid_validation_ndcg'] > decision['content_validation_ndcg']
    if (decision['default_model'] != ('hybrid' if strict else 'content')
            or decision['strict_validation_improvement'] is not strict
            or decision['test_used_for_selection'] is not False
            or manifest['default_model'] != decision['default_model']
            or manifest['selected_cf_weight'] != decision['selected_cf_weight']
            or name_for(manifest['selected_cf_weight']) != decision['selected_hybrid']):
        raise ValueError('Saved default does not satisfy the strict validation gate')
    for path,digest in manifest['component_file_sha256'].items():
        if prep.sha256(prep.require_local(path)) != digest:
            raise ValueError('Referenced frozen component artifact changed')
    cf,cb,_ = load_components(manifest['content_directory'],manifest['cf_directory'],expected_catalog,expected_content)
    if manifest['rank_constant'] != RANK_CONSTANT:
        raise ValueError('Unexpected RRF constant')
    if not challenger and manifest['default_model']=='content':
        return cb
    return HybridRecommender(cf,cb,manifest['selected_cf_weight'])
