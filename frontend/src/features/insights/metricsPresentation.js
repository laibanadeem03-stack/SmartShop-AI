export const MODEL_ORDER = ['count','cf','content','hybrid'];
export const MODEL_LABELS = { count:'Popularity', cf:'Collaborative filtering', content:'Content-based', hybrid:'Hybrid' };
export const MODEL_SHORT = { count:'Popularity', cf:'CF', content:'Content', hybrid:'Hybrid' };
export const MODEL_COLORS = { count:'#64748b', cf:'#27728a', content:'#0f766e', hybrid:'#4338ca' };
export const METRICS = [
  { key:'recall_at_10', title:'Recall@10', unit:'Decimal · macro average', description:'For each evaluated user, the share of relevant held-out products found in the top 10, then averaged across users. Higher means more of those products were retrieved.' },
  { key:'ndcg_at_10', title:'NDCG@10', unit:'Decimal · macro average', description:'Measures how highly relevant products appear in the top 10, relative to an ideal ordering for each user, then averaged across users. Earlier relevant results receive more credit.' },
  { key:'catalog_coverage_at_10', title:'Catalog coverage', unit:'Percent of training catalog', description:'The share of the frozen training catalog appearing at least once in these users’ top-10 lists. It measures recommendation breadth, not relevance or cold-product reachability.' },
];
export const SEGMENTS = {
  overall:'Overall', warm_users:'Warm users', cold_users:'Cold users',
  warm_user_warm_product:'Warm users · warm products', warm_user_cold_product:'Warm users · cold products',
  cold_user_warm_product:'Cold users · warm products', cold_user_cold_product:'Cold users · cold products',
  history_0:'History: 0 interactions', history_1_2:'History: 1–2 interactions', history_3_4:'History: 3–4 interactions', history_5_plus:'History: 5+ interactions',
};
export const segmentLabel = key => SEGMENTS[key] || key.replaceAll('_',' ');
export const splitLabel = split => split === 'validation' ? 'Validation' : 'Test';
export const formatCount = count => count == null ? 'Not reported' : count.toLocaleString('en-US');
export function formatMetric(value, key, exact = false) {
  if (value == null) return 'Not reported';
  if (key === 'catalog_coverage_at_10' || key.startsWith('fraction_')) return `${(value*100).toFixed(2)}%`;
  return exact ? String(value) : value.toFixed(8);
}
export function overallRows(data, split) {
  return MODEL_ORDER.flatMap(model => {
    const row = data.models.find(row => row.model === model && row.split === split);
    return row ? [{ ...row, overall: row.segments.find(segment => segment.segment === 'overall') ?? null }] : [];
  });
}
export function chartRows(rows, key) {
  return rows.map(row => ({ model:row.model, name:MODEL_SHORT[row.model], raw:row.overall?.[key] ?? null, value:row.overall?.[key] == null ? null : row.overall[key] * (key === 'catalog_coverage_at_10' ? 100 : 1) }));
}
export function metricSummary(rows, key, split) {
  const values = rows.map(row => row.overall?.[key]).filter(value => value != null);
  if (!values.length) return `No values reported for ${splitLabel(split)} overall.`;
  const range = `${formatMetric(Math.min(...values),key)} to ${formatMetric(Math.max(...values),key)}`;
  return `${splitLabel(split)} overall: ${values.length} reported model values, ranging from ${range}. ${key === 'catalog_coverage_at_10' ? 'Broader coverage does not imply better ranking quality.' : 'Higher values indicate stronger retrieval on this offline evaluation.'}`;
}
