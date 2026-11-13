// Verified in the read-only catalog. Featured, not exhaustive: no facets API exists.
export const FEATURED_CATEGORIES = ['Cases, Holsters & Sleeves', 'Screen Protectors',
  'Chargers & Power Adapters', 'Smartwatch Accessories', 'Automobile Accessories'];
const normalize = value => value.trim().toLowerCase().replace(/\s+/g, ' ');
export function parseFilters(search) {
  const params = new URLSearchParams(search);
  const categoryInput = params.get('category') || '';
  const category = FEATURED_CATEGORIES.find(c => normalize(c) === normalize(categoryInput)) || '';
  const rawPage = params.get('page') || '1';
  const n = /^\d+$/.test(rawPage) ? Number(rawPage) : 1;
  return { q: (params.get('q') || '').slice(0, 200).trim(), category,
    page: Number.isSafeInteger(n) && n >= 1 && n <= 1000000 ? n : 1,
    unknownCategory: !!categoryInput && !category };
}
export function filterParams({ q, category, page }) {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (category) params.set('category', category);
  params.set('page', String(page));
  return params;
}
