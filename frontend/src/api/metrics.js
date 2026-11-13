import { API_BASE_URL, ApiError } from './catalog.js';
import { MODELS } from './recommendations.js';

const invalid = () => new ApiError('INVALID_RESPONSE', 'The saved evaluation report could not be displayed. Please try again.');
function fraction(value) {
  if (value === undefined || value === null) return null;
  if (!Number.isFinite(value) || value < 0 || value > 1) throw invalid();
  return value;
}
function count(value) {
  if (value === undefined || value === null) return null;
  if (!Number.isSafeInteger(value) || value < 0) throw invalid();
  return value;
}
function text(value) {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string') throw invalid();
  return value;
}
export function validateMetrics(data, model) {
  if (!data || !Array.isArray(data.models)) throw invalid();
  const rows = new Set();
  const models = data.models.map(row => {
    if (!row || !Object.hasOwn(MODELS,row.model) || (model && row.model !== model) || !['validation','test'].includes(row.split) || !Array.isArray(row.segments) || rows.has(`${row.model}:${row.split}`)) throw invalid();
    rows.add(`${row.model}:${row.split}`);
    const segments = new Set();
    return { model: row.model, split: row.split,
      fraction_users_personalized: fraction(row.fraction_users_personalized), fraction_fallback_slots: fraction(row.fraction_fallback_slots),
      segments: row.segments.map(segment => {
        if (!segment || typeof segment.segment !== 'string' || !/^[a-z0-9_]{1,80}$/.test(segment.segment) || segments.has(segment.segment)) throw invalid();
        segments.add(segment.segment);
        return { segment: segment.segment, evaluated_users: count(segment.evaluated_users), recall_at_10: fraction(segment.recall_at_10), ndcg_at_10: fraction(segment.ndcg_at_10), catalog_coverage_at_10: fraction(segment.catalog_coverage_at_10) };
      }),
    };
  });
  if (data.default_model != null && !Object.hasOwn(MODELS,data.default_model)) throw invalid();
  if (data.limitations != null && (!Array.isArray(data.limitations) || !data.limitations.every(note => typeof note === 'string'))) throw invalid();
  return { evaluation: text(data.evaluation), candidate_products: count(data.candidate_products), serving_history_policy: text(data.serving_history_policy), metrics_history_policy: text(data.metrics_history_policy), relevance: text(data.relevance), default_model: data.default_model ?? null, limitations: data.limitations ?? [], models };
}
export async function loadMetrics(signal, model) {
  if (model && !Object.hasOwn(MODELS,model)) throw invalid();
  let response;
  try { response = await fetch(`${API_BASE_URL}/metrics/models${model ? '/'+model : ''}`, { signal, headers: { Accept:'application/json' } }); }
  catch (error) { if (signal?.aborted) throw error; throw new ApiError('CONNECTION_ERROR', 'We couldn’t connect to the local evaluation service. Check that the API is running, then retry.'); }
  if (!response.ok) throw new ApiError('UNAVAILABLE', 'Saved evaluation metrics are unavailable. Please try again.', response.status);
  let data;
  try { data = await response.json(); } catch (error) { if (signal?.aborted) throw error; throw invalid(); }
  return validateMetrics(data,model);
}
