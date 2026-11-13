import { expect,it } from 'vitest';
import { chartRows,formatMetric,metricSummary,overallRows,segmentLabel } from './metricsPresentation.js';
import { metricsFixture } from '../../test/metricsFixtures.js';
it('formats ranking metrics as decimals, coverage as percentages and missing data as unreported',()=>{
  expect(formatMetric(.00314159265,'recall_at_10')).toBe('0.00314159');expect(formatMetric(.00314159265,'ndcg_at_10',true)).toBe('0.00314159265');expect(formatMetric(.7361,'catalog_coverage_at_10')).toBe('73.61%');expect(formatMetric(0,'ndcg_at_10')).toBe('0.00000000');expect(formatMetric(null,'ndcg_at_10')).toBe('Not reported');
});
it('selects only the requested split and keeps a fixed model order without sorting by performance',()=>{
  const f=metricsFixture();f.models.reverse();const rows=overallRows(f,'validation');expect(rows.map(r=>r.model)).toEqual(['count','cf','content','hybrid']);expect(rows.every(r=>r.split==='validation')).toBe(true);expect(rows[0].overall.recall_at_10).toBe(.002);
});
it('uses exact source decimals in charts and converts only coverage units',()=>{
  const rows=overallRows(metricsFixture(),'test');expect(chartRows(rows,'ndcg_at_10').map(r=>r.value)).toEqual([.0005,.001,.0015,.002]);expect(chartRows(rows,'catalog_coverage_at_10').map(r=>r.value)).toEqual(rows.map(r=>r.overall.catalog_coverage_at_10*100));rows[0].overall.recall_at_10=null;expect(chartRows(rows,'recall_at_10')[0].value).toBeNull();
});
it('summarizes only provided values and labels unfamiliar segments without fabricating counts',()=>{
  expect(metricSummary(overallRows(metricsFixture(),'test'),'ndcg_at_10','test')).toContain('4 reported model values');expect(metricSummary([],'recall_at_10','test')).toBe('No values reported for Test overall.');expect(segmentLabel('new_bucket')).toBe('new bucket');
});
