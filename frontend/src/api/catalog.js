export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');
export const PAGE_SIZE = 24;
export class ApiError extends Error {
  constructor(code, message, status = 0) { super(message); this.name = 'ApiError'; this.code = code; this.status = status; }
}
const invalid = () => new ApiError('INVALID_RESPONSE', 'The catalog response could not be displayed. Please try again.');
async function getJSON(path, signal) {
  let response;
  try { response = await fetch(`${API_BASE_URL}${path}`, { signal, headers: { Accept: 'application/json' } }); }
  catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError('CONNECTION_ERROR', 'We couldn’t connect to the local catalog. Check that the API is running, then retry.');
  }
  if (!response.ok) {
    if (response.status === 404) throw new ApiError('NOT_FOUND', 'This product could not be found in the catalog.', 404);
    if (response.status === 409) throw new ApiError('OUTSIDE_CATALOG', 'This product is outside the frozen similarity catalog.', 409);
    if (response.status === 422) throw new ApiError('INVALID_REQUEST', 'The request could not be accepted. Clear the filters and try again.', 422);
    throw new ApiError('UNAVAILABLE', 'The catalog service is unavailable. Please try again.', response.status);
  }
  try { return await response.json(); }
  catch (error) { if (signal?.aborted) throw error; throw invalid(); }
}
export function validProduct(p) {
  return !!p && typeof p.product_id === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(p.product_id) &&
    typeof p.title === 'string' && typeof p.title_available === 'boolean' && typeof p.recommendation_eligible === 'boolean' &&
    (p.main_category === null || typeof p.main_category === 'string') && Array.isArray(p.categories) && p.categories.every(c => typeof c === 'string');
}
export async function loadReadiness(signal) {
  const health = await getJSON('/health/ready', signal);
  if (health?.status !== 'ready') throw new ApiError('NOT_READY', 'The catalog service is not ready yet. Please try again.');
  return health;
}
export async function loadProducts({ q = '', category = '', page = 1 }, signal) {
  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (q) query.set('q', q);
  if (category) query.set('category', category);
  const result = await getJSON(`/products?${query}`, signal);
  if (!Number.isSafeInteger(result?.total) || result.total < 0 || result.page !== page || result.page_size !== PAGE_SIZE ||
      !Array.isArray(result.items) || result.items.length > PAGE_SIZE || result.items.length > result.total ||
      !result.items.every(validProduct) || new Set(result.items.map(p => p.product_id)).size !== result.items.length) throw invalid();
  return result;
}
export async function loadProduct(productId, signal) {
  const p = await getJSON(`/products/${encodeURIComponent(productId)}`, signal);
  if (!validProduct(p) || p.product_id !== productId ||
      !(p.training_interaction_count === null || (Number.isSafeInteger(p.training_interaction_count) && p.training_interaction_count >= 0)) ||
      !(p.training_mean_rating === null || (Number.isFinite(p.training_mean_rating) && p.training_mean_rating >= 1 && p.training_mean_rating <= 5))) throw invalid();
  return p;
}
export async function loadSimilarProducts(productId, signal) {
  const result = await getJSON(`/products/${encodeURIComponent(productId)}/similar`, signal);
  if (result?.product_id !== productId || result.model !== 'content' || !Array.isArray(result.items) || result.items.length > 10 ||
      result.items.some((item, i) => !item || !validProduct(item.product) || !item.product.recommendation_eligible ||
        item.product.product_id === productId || item.rank !== i + 1 || !Number.isFinite(item.score) || item.score <= 0 || item.score_type !== 'cosine_similarity') ||
      new Set(result.items.map(item => item.product.product_id)).size !== result.items.length) throw invalid();
  return result;
}
