import { expect,it,vi } from 'vitest';
import { createDemoUser,loadExplanation,loadProfiles,loadRecommendations } from './recommendations.js';
import { products,response } from '../test/fixtures.js';
import { explanation,newUser,profiles,recommendations } from '../test/recommendationFixtures.js';

it('validates public profiles and makes only the explicit empty-body creation request',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response({items:profiles,total:12})).mockResolvedValueOnce(response(newUser,201));vi.stubGlobal('fetch',fetch);
  expect((await loadProfiles()).total).toBe(12);expect((await createDemoUser()).profile_type).toBe('new_demo');
  expect(fetch.mock.calls[1][1]).toMatchObject({method:'POST',body:'{}',headers:{'Content-Type':'application/json'}});
});
it('rejects invalid aliases without making a request',async()=>{
  vi.stubGlobal('fetch',vi.fn());await expect(loadRecommendations('../private','hybrid')).rejects.toMatchObject({code:'INVALID_RESPONSE'});expect(fetch).not.toHaveBeenCalled();
});
it('rejects malformed counts, duplicate products, wrong ordering and unknown sources',async()=>{
  for(const mutate of [b=>b.personalized_count=7,b=>b.items[1].product=b.items[0].product,b=>b.items[0].rank=2,b=>b.items[0].source='invented',b=>b.public_user_id='another',b=>b.items[0].product=products[1]]) {
    const b=recommendations();mutate(b);vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(b)));await expect(loadRecommendations('demo_1','hybrid')).rejects.toMatchObject({code:'INVALID_RESPONSE'});
  }
});
it('rejects explanations for a different batch, item, model, score or source',async()=>{
  const b=recommendations();
  for(const mutate of [e=>e.batch_id='wrong',e=>e.product=products[3],e=>e.model='count',e=>e.ranking_score=99,e=>e.source='content',e=>e.content_support.top_shared_features[0].dot_product_contribution=-1]) {
    const e=explanation(b,b.items[0].product.product_id);mutate(e);vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response(e)));await expect(loadExplanation(b.batch_id,b.items[0],b.model)).rejects.toMatchObject({code:'INVALID_RESPONSE'});
  }
});
it('retains recognized expiry codes but never internal server messages',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response({error:{code:'BATCH_NOT_FOUND',message:'PRIVATE_PATH'}},404)));
  await expect(loadProfiles()).rejects.toMatchObject({code:'BATCH_NOT_FOUND',status:404});
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response({error:{code:'PRIVATE_CODE',message:'PRIVATE_PATH'}},500)));
  await expect(loadProfiles()).rejects.toMatchObject({code:'UNAVAILABLE',message:'The recommendation service is unavailable. Please try again.'});
});
it('preserves abort signals and converts connection failures into safe errors',async()=>{
  const controller=new AbortController();const fetch=vi.fn().mockRejectedValue(new Error('PRIVATE_EXCEPTION'));vi.stubGlobal('fetch',fetch);
  await expect(loadProfiles(controller.signal)).rejects.toMatchObject({code:'CONNECTION_ERROR'});expect(fetch.mock.calls[0][1].signal).toBe(controller.signal);
});
