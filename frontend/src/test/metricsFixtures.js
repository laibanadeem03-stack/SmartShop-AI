// Synthetic evaluation aggregates only; runtime code never imports these fixtures.
export function metricsFixture(model) {
  const rows=['count','cf','content','hybrid'].flatMap((name,index)=>['validation','test'].map(split=>({
    model:name,split,fraction_users_personalized:index===0?0:.7,fraction_fallback_slots:index===0?1:.3,
    segments:[
      {segment:'overall',evaluated_users:split==='test'?20:30,recall_at_10:(index+1)*(split==='test'?.001:.002),ndcg_at_10:(index+1)*(split==='test'?.0005:.001),catalog_coverage_at_10:index*.2},
      {segment:'warm_users',evaluated_users:15,recall_at_10:.01234567890123456,ndcg_at_10:.004,catalog_coverage_at_10:.4},
      {segment:'cold_users',evaluated_users:5,recall_at_10:0,ndcg_at_10:0,catalog_coverage_at_10:.01},
      {segment:'warm_user_cold_product',evaluated_users:7,recall_at_10:0,ndcg_at_10:0,catalog_coverage_at_10:.25},
      {segment:'history_0',evaluated_users:5,recall_at_10:0,ndcg_at_10:0,catalog_coverage_at_10:.01},
      {segment:'history_1_2',evaluated_users:2,recall_at_10:.002,ndcg_at_10:null,catalog_coverage_at_10:null},
    ],
  })));
  return {evaluation:'saved_global_chronological_80_10_10',candidate_products:100,serving_history_policy:'training_snapshot',metrics_history_policy:'validation excludes train; test excludes train and validation',relevance:'ratings_4_or_5',default_model:'hybrid',models:rows.filter(row=>!model||row.model===model),limitations:['Synthetic saved limitation from the API.']};
}
