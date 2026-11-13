"""An allowlist of saved retrospective aggregates, never prediction rows."""
from copy import deepcopy

NAMES = {'count':'count', 'cf':'item_cf_k50_lambda10',
         'content':'tfidf_df2_title80', 'hybrid':'hybrid_cf50'}
SEGMENTS = ('overall','warm_users','cold_users','warm_user_warm_product',
            'warm_user_cold_product','cold_user_warm_product','cold_user_cold_product',
            'history_0','history_1_2','history_3_4','history_5_plus')


def aggregate_performance(saved):
    rows = []
    for public, name in NAMES.items():
        for window in ('validation','test'):
            data = saved[window][name]
            segments = []
            for segment in SEGMENTS:
                raw = data['segments'][segment]
                segments.append({'segment':segment, 'evaluated_users':raw['evaluated_users'],
                                 'recall_at_10':raw['recall_at_10'],'ndcg_at_10':raw['ndcg_at_10'],
                                 'catalog_coverage_at_10':raw['catalog_coverage_at_10']})
            usage = data.get('personalization')
            rows.append({'model':public,'split':window,'segments':segments,
                         'fraction_users_personalized':usage['fraction_users_personalized'] if usage else 0.0,
                         'fraction_fallback_slots':usage['fraction_fallback_slots'] if usage else 1.0})
    return {'evaluation':'saved_global_chronological_80_10_10', 'candidate_products':11012,
            'serving_history_policy':'training_snapshot', 'metrics_history_policy':'validation excludes train; test excludes train and validation',
            'relevance':'ratings_4_or_5', 'default_model':'hybrid','models':rows,
            'limitations':['Retrospective five-core selection uses future activity.',
                           'Metadata may postdate the training cutoff.',
                           'Products outside the training catalog remain unreachable.',
                           'Validation was reused for component and hybrid selection.',
                           'Point estimates are not evidence of statistical significance or online performance.']}


class MetricsService:
    def __init__(self, performance):
        if performance is None:
            raise ValueError('Aggregate results are required')
        self.performance = deepcopy(performance)

    def results(self, model=None):
        result = deepcopy(self.performance)
        if model is not None:
            result['models'] = [row for row in result['models'] if row['model']==model]
        return result
