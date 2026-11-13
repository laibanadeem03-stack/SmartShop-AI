import { products, response, mockCatalog } from './fixtures.js';
export const profiles = Array.from({length:12},(_,i) => ({public_user_id:`demo_${i+1}`,label:`Historical profile ${i+1}`,profile_type:'dataset_backed',activity:i%2?'active':'light'}));
export const newUser = {public_user_id:'new_synthetic',label:'New demo user',profile_type:'new_demo'};
export function recommendations(alias='demo_1',model='hybrid',batch='batch_1',chosen=[products[4],products[0]]) {
  const cold=alias.startsWith('new_'),served=cold?'count':model;
  const source=cold?'popularity_fallback':({hybrid:'hybrid_both',content:'content',cf:'cf',count:'count_popularity'})[served];
  return {batch_id:batch,public_user_id:alias,requested_model:model,model:served,model_version:served+'-v1',history_policy:'training_snapshot',cold_start:cold,
    returned_count:chosen.length,personalized_count:served==='count'?0:chosen.length,fallback_count:served==='count'?chosen.length:0,
    items:chosen.map((product,i)=>({rank:i+1,product,score:served==='count'?57-i:.02-i*.001,score_type:({hybrid:'normalized_weighted_rrf',content:'cosine_similarity',cf:'positive_cosine_sum',count:'training_interaction_count'})[served],source}))};
}
export function explanation(batch, productId) {
  const item=batch.items.find(i=>i.product.product_id===productId);
  const data={batch_id:batch.batch_id,product:item.product,model:batch.model,source:item.source,ranking_score:item.score,score_type:item.score_type,reasons:['Synthetic verified reason from the API.']};
  if(batch.model==='count')data.count_evidence={training_interaction_count:item.score};
  if(['hybrid','cf'].includes(batch.model)) data.cf_support={seed_contributions:[{product:products[3],similarity:.3}],total_seed_similarity:.8};
  if(['hybrid','content'].includes(batch.model)) data.content_support={top_shared_features:[{field:'title',term:'zx-42',dot_product_contribution:.03}],total_feature_contribution:.2};
  if(batch.model==='hybrid')data.fusion={rank_constant:60,configured_cf_weight:.5,effective_cf_weight:.5,effective_content_weight:.5,cf_rank:3,content_rank:7,cf_rank_contribution:.011,content_rank_contribution:.009};
  return data;
}
export function mockRecommendations(vi, override) {
  const base=mockCatalog(vi),batches=new Map();let counter=0;
  return vi.fn(async(raw,options)=>{
    const url=new URL(raw);
    const custom=override?.(url,options,batches);
    if(custom!==undefined)return custom;
    if(url.pathname.endsWith('/demo/profiles'))return response({items:profiles,total:12});
    if(url.pathname.endsWith('/demo/users'))return response(newUser,201);
    const match=url.pathname.match(/\/users\/([^/]+)\/recommendations$/);
    if(match){const b=recommendations(match[1],url.searchParams.get('model'),'batch_'+(++counter));batches.set(b.batch_id,b);return response(b);}
    const e=url.pathname.match(/\/recommendations\/([^/]+)\/items\/([^/]+)\/explanation$/);
    if(e)return response(explanation(batches.get(e[1]),e[2]));
    return base(raw,options);
  });
}
