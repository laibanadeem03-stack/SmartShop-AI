// Synthetic test-only records. No running application imports this module.
export const products = Array.from({ length: 50 }, (_, i) => ({
  product_id: `TEST_${String(i).padStart(3, '0')}`,
  title: i === 0 ? 'Synthetic test USB-C cable ZX-42' : i === 2 ? 'Title unavailable' : `Synthetic test product ${String(i).padStart(2, '0')}`,
  title_available: i !== 2,
  main_category: i === 2 ? null : 'Accessories',
  categories: i === 2 ? [] : ['Accessories', i % 2 ? 'Screen Protectors' : 'Cables'],
  recommendation_eligible: i !== 1,
}));
export function page(items = products.slice(0,24), total = 50, current = 1) {
  return { items, total, page: current, page_size: 24 };
}
export function detail(product = products[0]) {
  return { ...product, training_interaction_count: product.recommendation_eligible ? 17 : null,
    training_mean_rating: product.recommendation_eligible ? 4.25 : null };
}
export function similar(productId, neighbors = [products[3],products[4]]) {
  return { product_id:productId, model:'content',items:neighbors.map((product,i) => ({ rank:i+1,product,score:0.8-i*0.1,score_type:'cosine_similarity' })) };
}
export function response(data, status = 200) { return { ok:status>=200&&status<300,status,json:async()=>structuredClone(data) }; }
const normalized = s => s.trim().toLowerCase().replace(/\s+/g,' ');
export function mockCatalog(vi) {
  return vi.fn(async raw => {
    const url = new URL(raw);
    if (url.pathname.endsWith('/health/ready')) return response({status:'ready'});
    if (url.pathname.endsWith('/demo/profiles')) return response({items:[],total:0});
    if (url.pathname.endsWith('/metrics/models')) return response({models:[]});
    if (url.pathname.endsWith('/products')) {
      const q = normalized(url.searchParams.get('q')||'');
      const category = normalized(url.searchParams.get('category')||'');
      const current = Number(url.searchParams.get('page')||1);
      const filtered = products.filter(p => normalized([p.title,p.main_category,...p.categories].filter(Boolean).join(' ')).includes(q) &&
        (!category || [p.main_category,...p.categories].filter(Boolean).some(c=>normalized(c)===category)));
      return response(page(filtered.slice((current-1)*24,current*24),filtered.length,current));
    }
    const match = url.pathname.match(/\/products\/([^/]+)(\/similar)?$/);
    if (match) {
      const product=products.find(p=>p.product_id===decodeURIComponent(match[1]));
      if (!product) return response({error:{message:'PRIVATE_INTERNAL_DETAIL'}},404);
      if (!match[2]) return response(detail(product));
      if (!product.recommendation_eligible) return response({},409);
      return response(similar(product.product_id,product.product_id===products[2].product_id?[]:[products[3],products[4]].filter(p=>p.product_id!==product.product_id)));
    }
    throw new Error('Unexpected endpoint in frontend test');
  });
}
