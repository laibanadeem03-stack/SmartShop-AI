"""Serialized adapters around the original frozen inference/evidence methods."""
from copy import deepcopy
import math

from ..errors import ApiError
from .batch_cache import Batch


def score_type(model, source):
    if model == 'count':
        return 'training_interaction_count'
    if source == 'popularity_fallback':
        return 'fallback_zero'
    return {'hybrid':'normalized_weighted_rrf','cf':'positive_cosine_sum','content':'cosine_similarity'}[model]


class RecommendationService:
    def __init__(self, registry, repository, identities, cache):
        self.registry, self.repository, self.identities, self.cache = registry, repository, identities, cache
        self.hybrid = registry.model

    def _clear_transient(self):
        self.hybrid.last_signals = None
        self.hybrid.last_evidence = []
        self.hybrid.last_sources = []
        self.hybrid.latencies_ns.clear()
        self.hybrid.cf.last_sources = []
        self.hybrid.content.last_sources = []

    def _rank(self, user, seen, model):
        if model == 'hybrid':
            results = self.hybrid.recommend_prepared(self.hybrid.prepare(user,seen),seen,10)
            return results, list(self.hybrid.last_sources), deepcopy(self.hybrid.last_evidence)
        if model == 'count':
            import popularity_baseline
            results = popularity_baseline.recommend(self.hybrid.fallback,seen,10)
            return results, ['count_popularity']*len(results), []
        engine = self.hybrid.cf if model == 'cf' else self.hybrid.content
        results = engine(user,seen,10)
        sources = ['cf' if s=='collaborative' else s for s in engine.last_sources]
        return results, sources, []

    def recommend(self, alias, requested_model='hybrid'):
        user, cold = self.identities.resolve(alias)
        model = 'count' if cold else requested_model
        # No runtime event, validation or test history is added to this mask.
        seen = frozenset(self.hybrid.snapshot['seen'].get(user,()))
        with self.registry.inference_lock:
            try:
                results, sources, traces = self._rank(user,seen,model)
                if cold:
                    sources = ['popularity_fallback']*len(results)
                if (len(results)>10 or len({p for p,_ in results})!=len(results)
                        or any(p in seen or p not in self.hybrid.index or not math.isfinite(s) or s<0 for p,s in results)):
                    raise ValueError('Invalid frozen-model output')
                batch_id = self.cache.put(Batch(user,model,seen,tuple(results),tuple(sources),tuple(traces)))
            finally:
                self._clear_transient()
        products = self.repository.product_summaries([p for p,_ in results])
        personalized = sum(s not in ('count_popularity','popularity_fallback') for s in sources)
        return {'batch_id':batch_id,'public_user_id':alias,'requested_model':requested_model,'model':model,
                'model_version':model+'-v1','history_policy':'training_snapshot','cold_start':cold,
                'returned_count':len(results),'personalized_count':personalized,'fallback_count':len(results)-personalized,
                'items':[{'rank':i,'product':products[p],'score':s,'score_type':score_type(model,source),'source':source}
                         for i,((p,s),source) in enumerate(zip(results,sources),1)]}

    def similar(self, identifier):
        product = self.repository.product(identifier)
        if product is None:
            raise ApiError(404,'PRODUCT_NOT_FOUND','Product not found.')
        if identifier not in self.hybrid.index:
            raise ApiError(409,'PRODUCT_NOT_IN_MODEL_CATALOG','This product is outside the frozen recommendation catalog.')
        with self.registry.inference_lock:
            results = self.hybrid.content.similar_items(identifier,10)
        products = self.repository.product_summaries([p for p,_ in results])
        return {'product_id':identifier,'model':'content',
                'items':[{'rank':i,'product':products[p],'score':s,'score_type':'cosine_similarity'}
                         for i,(p,s) in enumerate(results,1)]}

    def explain(self, batch_id, product):
        batch = self.cache.get(batch_id)
        position = next((i for i,(p,_) in enumerate(batch.results) if p==product),None)
        if position is None:
            raise ApiError(404,'RECOMMENDATION_NOT_FOUND','Product was not returned in this recommendation batch.')
        _, score = batch.results[position]
        source = batch.sources[position]
        with self.registry.inference_lock:
            try:
                result = {'batch_id':batch_id,'product':self.repository.product_summaries([product])[product],
                          'model':batch.model,'source':source,'ranking_score':score,
                          'score_type':score_type(batch.model,source),'reasons':[]}
                if source in ('count_popularity','popularity_fallback'):
                    count = self.hybrid.snapshot['items'][product]['count']
                    if score != (float(count) if batch.model=='count' else 0.0):
                        raise ValueError('Count/fallback evidence score mismatch')
                    result['count_evidence'] = {'training_interaction_count':count}
                    result['reasons'] = [(f'Filled by frozen count-popularity fallback using {count} training rating interactions.'
                                          if source=='popularity_fallback' else
                                          f'Ranked by its {count} rating interactions in the frozen training data.')]
                    return result
                signals = self.hybrid.prepare(batch.private_user,batch.seen)
                # Replay the same native engine before explaining any returned item.
                replay = (self.hybrid.recommend_prepared(signals,batch.seen,10) if batch.model=='hybrid'
                          else self._rank(batch.private_user,batch.seen,batch.model)[0])
                if tuple(replay) != batch.results:
                    raise ValueError('Recommendation batch no longer matches frozen model')
                if batch.model == 'hybrid':
                    trace = batch.traces[position]
                else:
                    # Reuse verified support arithmetic from the existing evidence
                    # helper, but expose only evidence used by the requested model.
                    weights = self.hybrid.effective_weights(signals)
                    probe = self.hybrid._trace(product,signals,weights,0.0)
                    fused_score = probe['cf_rank_contribution']+probe['content_rank_contribution']
                    trace = self.hybrid._trace(product,signals,weights,fused_score)
                evidence = self.hybrid.explain(batch.private_user,trace,signals=signals)
                if batch.model in ('hybrid','cf') and evidence.get('cf_support'):
                    support = deepcopy(evidence['cf_support'])
                    products = self.repository.product_summaries([s['seed_product'] for s in support['seed_contributions']])
                    support['seed_contributions'] = [{'product':products[s['seed_product']], 'similarity':s['similarity']}
                                                     for s in support['seed_contributions']]
                    result['cf_support'] = support
                    result['reasons'].append('Supported by positive training-rating patterns linked to the listed seed products.')
                    if batch.model=='cf' and not math.isclose(score,support['total_seed_similarity'],rel_tol=1e-12,abs_tol=1e-12):
                        raise ValueError('CF explanation score mismatch')
                if batch.model in ('hybrid','content') and evidence.get('content_support'):
                    result['content_support'] = evidence['content_support']
                    result['reasons'].append('Shares the listed title/category features with the frozen positive-training profile.')
                    if batch.model=='content' and not math.isclose(score,evidence['content_support']['total_feature_contribution'],rel_tol=1e-6,abs_tol=1e-6):
                        raise ValueError('Content explanation score mismatch')
                if batch.model=='hybrid':
                    result['fusion'] = {k:evidence[k] for k in ('configured_cf_weight','effective_cf_weight',
                        'effective_content_weight','cf_rank','content_rank','cf_rank_contribution','content_rank_contribution')}
                    result['fusion']['rank_constant'] = 60
                if not result['reasons']:
                    raise ValueError('Personalized recommendation has no verified support')
                return result
            finally:
                self._clear_transient()
