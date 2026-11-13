import { expect,it,vi } from 'vitest';
import { loadMetrics,validateMetrics } from './metrics.js';
import { metricsFixture } from '../test/metricsFixtures.js';
import { response } from '../test/fixtures.js';

it('loads aggregate and exact per-model endpoints with cancellation signals',async()=>{
  const fetch=vi.fn().mockResolvedValueOnce(response(metricsFixture())).mockResolvedValueOnce(response(metricsFixture('cf')));vi.stubGlobal('fetch',fetch);const controller=new AbortController();
  expect((await loadMetrics(controller.signal)).models).toHaveLength(8);expect((await loadMetrics(controller.signal,'cf')).models).toHaveLength(2);
  expect(fetch.mock.calls[0][0]).toMatch(/\/metrics\/models$/);expect(fetch.mock.calls[1][0]).toMatch(/\/metrics\/models\/cf$/);expect(fetch.mock.calls[0][1].signal).toBe(controller.signal);
});
it('preserves precision, nulls, actual zero and missing fields independently',()=>{
  const fixture=metricsFixture();delete fixture.models[0].segments[0].ndcg_at_10;delete fixture.candidate_products;
  const data=validateMetrics(fixture);expect(data.models[0].segments[0].ndcg_at_10).toBeNull();expect(data.models[0].segments[0].catalog_coverage_at_10).toBe(0);expect(data.candidate_products).toBeNull();expect(data.models[0].segments[1].recall_at_10).toBe(.01234567890123456);
});
it('accepts empty reports and zero-user nullable segments without inventing metrics',()=>{
  expect(validateMetrics({models:[]}).models).toEqual([]);const f=metricsFixture();f.models[0].segments[0]={segment:'overall',evaluated_users:0,recall_at_10:null,ndcg_at_10:null,catalog_coverage_at_10:0};expect(validateMetrics(f).models[0].segments[0].evaluated_users).toBe(0);
});
it('rejects out-of-range, nonnumeric, duplicate or inconsistent model rows',()=>{
  for(const mutate of [f=>f.models[0].segments[0].recall_at_10=1.1,f=>f.models[0].segments[0].ndcg_at_10='0.4',f=>f.models[0].segments[0].evaluated_users=-1,f=>f.models.push(f.models[0]),f=>f.models[0].segments.push(f.models[0].segments[0]),f=>f.models[0].split='live',f=>f.models[0].model='unknown']){
    const f=metricsFixture();mutate(f);expect(()=>validateMetrics(f)).toThrow('saved evaluation report');
  }
  expect(()=>validateMetrics(metricsFixture(),'cf')).toThrow();
});
it('sanitizes backend failures rather than displaying private errors or substituted values',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(response({error:{message:'PRIVATE_PATH'}},503)));await expect(loadMetrics()).rejects.toMatchObject({code:'UNAVAILABLE',message:'Saved evaluation metrics are unavailable. Please try again.'});
});
it('distinguishes connection failures, invalid JSON, and intentional aborts',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('PRIVATE')));await expect(loadMetrics()).rejects.toMatchObject({code:'CONNECTION_ERROR'});
  const controller=new AbortController();controller.abort();await expect(loadMetrics(controller.signal)).rejects.toThrow('PRIVATE');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:()=>Promise.reject(new Error('PRIVATE'))}));await expect(loadMetrics()).rejects.toMatchObject({code:'INVALID_RESPONSE'});
});
