import { describe, expect, it, vi } from 'vitest';
import { ApiError, loadProducts, loadReadiness, loadProduct, loadSimilarProducts } from './catalog.js';
import { detail, mockCatalog, page, products, response, similar } from '../test/fixtures.js';

describe('catalog API contracts', () => {
  it('requests a server-side 24-product page with encoded search/category parameters', async () => {
    vi.stubGlobal('fetch',mockCatalog(vi));const signal=new AbortController().signal;
    await loadProducts({q:'USB-C & ZX-42 %_',category:'Screen Protectors',page:2},signal);
    const [raw,options]=fetch.mock.calls[0];const url=new URL(raw);
    expect(Object.fromEntries(url.searchParams)).toEqual({page:'2',page_size:'24',q:'USB-C & ZX-42 %_',category:'Screen Protectors'});
    expect(options.signal).toBe(signal);
  });
  it('preserves nullable metadata and model numbers', async () => {
    vi.stubGlobal('fetch',mockCatalog(vi));const data=await loadProducts({});
    expect(data.items[0].title).toContain('ZX-42');expect(data.items[2].main_category).toBeNull();
  });
  it('loads independent product details and validates historical statistics', async () => {
    vi.stubGlobal('fetch',mockCatalog(vi));expect(await loadProduct(products[0].product_id)).toEqual(detail());
    vi.stubGlobal('fetch',vi.fn(async()=>response({...detail(),training_mean_rating:8})));
    await expect(loadProduct(products[0].product_id)).rejects.toThrow('could not be displayed');
  });
  it('validates similarity ranking, identity, positive scores and zero results', async () => {
    vi.stubGlobal('fetch',mockCatalog(vi));expect((await loadSimilarProducts(products[0].product_id)).items).toHaveLength(2);
    expect((await loadSimilarProducts(products[2].product_id)).items).toEqual([]);
    for (const bad of [{...similar(products[0].product_id),product_id:'WRONG'},similar(products[0].product_id,[products[0]]),similar(products[0].product_id,[products[1]])]) {
      vi.stubGlobal('fetch',vi.fn(async()=>response(bad)));
      await expect(loadSimilarProducts(products[0].product_id)).rejects.toThrow('could not be displayed');
    }
  });
  it('rejects oversized, duplicate and misaligned pages', async () => {
    for(const bad of [page(Array(25).fill(products[0])),page([products[0],products[0]]),page([products[0]],50,2),page([{...products[0],categories:null}])]) {
      vi.stubGlobal('fetch',vi.fn(async()=>response(bad)));
      await expect(loadProducts({page:1})).rejects.toThrow('could not be displayed');
    }
  });
  it('sanitizes HTTP and network errors and retains status for UI handling', async () => {
    for(const status of [404,409,422,503]) {
      vi.stubGlobal('fetch',vi.fn(async()=>response({error:{message:'PRIVATE_PATH'}},status)));
      try { await loadProduct('UNKNOWN');throw new Error('Expected rejection'); }
      catch(error) { expect(error).toBeInstanceOf(ApiError);expect(error.status).toBe(status);expect(error.message).not.toContain('PRIVATE_PATH'); }
    }
    vi.stubGlobal('fetch',vi.fn(async()=>{throw new TypeError('PRIVATE_PATH');}));
    await expect(loadReadiness()).rejects.toThrow('connect to the local catalog');
  });
  it('does not disclose malformed JSON exception contents', async () => {
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>{throw new SyntaxError('PRIVATE_PATH');}})));
    await expect(loadReadiness()).rejects.toThrow('could not be displayed');
  });
  it('rejects a nonready success response', async () => {
    vi.stubGlobal('fetch',vi.fn(async()=>response({status:'alive'})));
    await expect(loadReadiness()).rejects.toThrow('not ready');
  });
});
