import { API_BASE_URL, ApiError, validProduct } from './catalog.js';

export const MODELS = { hybrid: 'Hybrid', content: 'Content-based', cf: 'Collaborative', count: 'Count popularity' };
export const SOURCES = { hybrid_both: 'Collaborative + content', cf_only: 'Collaborative signal', content_only: 'Content signal', cf: 'Collaborative', content: 'Content-based', count_popularity: 'Count popularity', popularity_fallback: 'Popularity fallback' };
const SCORE_TYPES = ['normalized_weighted_rrf', 'positive_cosine_sum', 'cosine_similarity', 'training_interaction_count', 'fallback_zero'];
export const validAlias = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);
const finite = value => Number.isFinite(value) && value >= 0;
const invalid = () => new ApiError('INVALID_RESPONSE', 'The recommendation response could not be displayed. Please try again.');
const messages = {
  USER_NOT_FOUND: 'This local demo profile is no longer available. Choose a historical profile or create a new one.',
  BATCH_NOT_FOUND: 'This explanation batch has expired or is no longer available.',
  RECOMMENDATION_NOT_FOUND: 'This item is no longer available in the explanation batch.',
  LOCAL_USER_LIMIT: 'The local demo-profile limit has been reached. Choose an existing historical profile.',
};
async function request(path, signal, method = 'GET') {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method, signal, headers: { Accept: 'application/json', ...(method === 'POST' ? { 'Content-Type': 'application/json' } : {}) }, ...(method === 'POST' ? { body: '{}' } : {}) });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError('CONNECTION_ERROR', 'We couldn’t connect to the local recommendation service. Check that the API is running, then retry.');
  }
  let body;
  try { body = await response.json(); } catch (error) { if (signal?.aborted) throw error; if (response.ok) throw invalid(); }
  if (!response.ok) {
    const code = body?.error?.code;
    // Never display server messages, paths, exception details or arbitrary error codes.
    if (Object.hasOwn(messages, code)) throw new ApiError(code, messages[code], response.status);
    throw new ApiError('UNAVAILABLE', 'The recommendation service is unavailable. Please try again.', response.status);
  }
  return body;
}
export async function loadProfiles(signal) {
  const data = await request('/demo/profiles', signal);
  if (!Array.isArray(data?.items) || data.total !== data.items.length || !data.items.every(p => validAlias(p.public_user_id) && typeof p.label === 'string' && p.profile_type === 'dataset_backed' && ['light','moderate','active'].includes(p.activity)) || new Set(data.items.map(p => p.public_user_id)).size !== data.total) throw invalid();
  return data;
}
export async function createDemoUser(signal) {
  const data = await request('/demo/users', signal, 'POST');
  if (!validAlias(data?.public_user_id) || data.profile_type !== 'new_demo' || typeof data.label !== 'string') throw invalid();
  return data;
}
export async function loadRecommendations(alias, model, signal) {
  if (!validAlias(alias) || !Object.hasOwn(MODELS, model)) throw invalid();
  const data = await request(`/users/${encodeURIComponent(alias)}/recommendations?model=${model}`, signal);
  if (!validAlias(data?.batch_id) || data.public_user_id !== alias || data.requested_model !== model || !Object.hasOwn(MODELS, data.model) ||
      typeof data.model_version !== 'string' || data.history_policy !== 'training_snapshot' || typeof data.cold_start !== 'boolean' ||
      (data.cold_start ? data.model !== 'count' : data.model !== model) || !Array.isArray(data.items) || data.items.length > 10 ||
      data.returned_count !== data.items.length || !Number.isSafeInteger(data.personalized_count) || data.personalized_count < 0 ||
      !Number.isSafeInteger(data.fallback_count) || data.fallback_count < 0 || data.personalized_count + data.fallback_count !== data.returned_count ||
      data.items.some((item,i) => !item || item.rank !== i+1 || !validProduct(item.product) || !item.product.recommendation_eligible || !finite(item.score) || !SCORE_TYPES.includes(item.score_type) || !Object.hasOwn(SOURCES,item.source)) ||
      new Set(data.items.map(item => item.product.product_id)).size !== data.items.length ||
      data.items.filter(item => !['count_popularity','popularity_fallback'].includes(item.source)).length !== data.personalized_count) throw invalid();
  return data;
}
export async function loadExplanation(batch, item, model, signal) {
  const data = await request(`/recommendations/${encodeURIComponent(batch)}/items/${encodeURIComponent(item.product.product_id)}/explanation`, signal);
  if (data?.batch_id !== batch || !validProduct(data.product) || data.product.product_id !== item.product.product_id || data.model !== model ||
      data.source !== item.source || data.score_type !== item.score_type || data.ranking_score !== item.score || !Array.isArray(data.reasons) || !data.reasons.every(r => typeof r === 'string') || !data.reasons.length) throw invalid();
  if (data.cf_support && (!finite(data.cf_support.total_seed_similarity) || !Array.isArray(data.cf_support.seed_contributions) || !data.cf_support.seed_contributions.every(s => validProduct(s.product) && finite(s.similarity)))) throw invalid();
  if (data.content_support && (!finite(data.content_support.total_feature_contribution) || !Array.isArray(data.content_support.top_shared_features) || !data.content_support.top_shared_features.every(f => ['title','category'].includes(f.field) && typeof f.term === 'string' && finite(f.dot_product_contribution)))) throw invalid();
  if (data.fusion && (data.fusion.rank_constant !== 60 || !['configured_cf_weight','effective_cf_weight','effective_content_weight','cf_rank_contribution','content_rank_contribution'].every(k => finite(data.fusion[k])) || !['cf_rank','content_rank'].every(k => data.fusion[k] === null || (Number.isSafeInteger(data.fusion[k]) && data.fusion[k] > 0)))) throw invalid();
  if (data.count_evidence && (!Number.isSafeInteger(data.count_evidence.training_interaction_count) || data.count_evidence.training_interaction_count < 1)) throw invalid();
  return data;
}
