import { act,fireEvent,render,screen,waitFor,within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach,expect,it,vi } from 'vitest';
import { ApiReadinessProvider } from '../../api/ApiReadinessProvider.jsx';
import { InsightsPage } from './InsightsPage.jsx';
import { metricsFixture } from '../../test/metricsFixtures.js';
import { response } from '../../test/fixtures.js';
function mockApi(override){return vi.fn((raw,options)=>{
  const url=new URL(raw),custom=override?.(url,options);if(custom!==undefined)return custom;
  if(url.pathname.endsWith('/health/ready'))return Promise.resolve(response({status:'ready'}));
  const model=url.pathname.match(/\/metrics\/models\/([^/]+)$/)?.[1];return Promise.resolve(response(metricsFixture(model)));
});}
const view=()=>render(<MemoryRouter><ApiReadinessProvider><InsightsPage/></ApiReadinessProvider></MemoryRouter>);
async function ready(){await screen.findByRole('combobox',{name:'Evaluation split'});await screen.findByRole('table',{name:/Hybrid — Test segment/});}
beforeEach(()=>{
  vi.stubGlobal('fetch',mockApi());
  vi.stubGlobal('ResizeObserver',class{constructor(callback){this.callback=callback;}observe(target){this.callback([{target,contentRect:{width:330,height:234}}]);}disconnect(){}});
});
it('renders actual API values in three charts, accessible tables and default metric cards',async()=>{
  view();await ready();expect(screen.getAllByRole('figure')).toHaveLength(3);expect(document.querySelectorAll('.recharts-surface')).toHaveLength(3);
  expect(screen.getByText('Historical Evaluation')).toBeInTheDocument();expect(screen.getByText('Hybrid is the selected default')).toBeInTheDocument();
  expect(document.querySelector('.insight-card-grid')).toHaveTextContent('0.00400000');expect(document.querySelector('.insight-card-grid')).toHaveTextContent('60.00%');
  expect(screen.getByRole('table',{name:/NDCG@10 — Test/})).toHaveTextContent('0.00200000');expect(screen.getByRole('table',{name:/Test overall evaluated-user counts/})).toHaveTextContent('20');
  expect(screen.getByText(/CF\/content fusion weights are not supplied/)).toBeInTheDocument();
});
it('switches validation/test consistently across charts, counts, cards and segments',async()=>{
  view();await ready();fireEvent.change(screen.getByRole('combobox',{name:'Evaluation split'}),{target:{value:'validation'}});
  expect(document.querySelector('.insights-dashboard')).toHaveAttribute('data-split','validation');expect(document.querySelector('.insight-card-grid')).toHaveTextContent('0.00800000');expect(document.querySelector('.insight-card-grid')).toHaveTextContent('30 evaluated users');
  expect(screen.getByRole('table',{name:/Recall@10 — Validation/})).toBeInTheDocument();expect(screen.getByRole('table',{name:/Hybrid — Validation segment/})).toBeInTheDocument();expect(screen.queryByRole('table',{name:/Hybrid — Test segment/})).not.toBeInTheDocument();
});
it('switches per-model segment endpoint without changing the default or split',async()=>{
  view();await ready();fireEvent.change(screen.getByRole('combobox',{name:'Segment analysis model'}),{target:{value:'cf'}});await screen.findByRole('table',{name:/Collaborative filtering — Test segment/});
  expect(fetch.mock.calls.some(([url])=>url.endsWith('/metrics/models/cf'))).toBe(true);expect(screen.getByText('Hybrid is the selected default')).toBeInTheDocument();
});
it('shows full precision on demand including original coverage fractions',async()=>{
  view();await ready();expect(screen.queryByText('0.01234567890123456')).not.toBeInTheDocument();fireEvent.click(screen.getByRole('checkbox',{name:'Show full API precision'}));
  expect(screen.getByText('0.01234567890123456')).toBeInTheDocument();expect(screen.getAllByText('API fraction: 0.4').length).toBeGreaterThan(0);
});
it('retains null/missing values as unreported while real zeros remain zero',async()=>{
  vi.stubGlobal('fetch',mockApi(url=>{const model=url.pathname.match(/\/models\/([^/]+)$/)?.[1];if(!url.pathname.includes('/metrics/'))return;const f=metricsFixture(model);for(const row of f.models){delete row.segments[0].recall_at_10;delete row.fraction_users_personalized;}return response(f);}));
  view();await ready();const recall=screen.getByRole('table',{name:/Recall@10 — Test/});expect(within(recall).getAllByText('Not reported')).toHaveLength(4);expect(screen.getByText('No values were supplied for this metric.')).toBeInTheDocument();
  expect(document.querySelector('[data-segment="cold_users"]')).toHaveTextContent('0.00000000');expect(document.querySelector('[data-segment="history_1_2"]')).toHaveTextContent('Not reported');
});
it('disables a split not supplied by the API and does not borrow metrics from another split',async()=>{
  vi.stubGlobal('fetch',mockApi(url=>{if(!url.pathname.includes('/metrics/'))return;const f=metricsFixture(url.pathname.match(/\/models\/([^/]+)$/)?.[1]);f.models=f.models.filter(row=>row.split==='validation');return response(f);}));
  view();await screen.findByRole('table',{name:/Hybrid — Validation segment/});expect(screen.getByRole('combobox',{name:'Evaluation split'})).toHaveValue('validation');expect(screen.getByRole('option',{name:'Test · not supplied'})).toBeDisabled();expect(screen.queryByRole('table',{name:/Recall@10 — Test/})).not.toBeInTheDocument();
});
it('handles an empty segment list and unknown saved segment labels honestly',async()=>{
  let empty=true;vi.stubGlobal('fetch',mockApi(url=>{if(!url.pathname.match(/\/models\//))return;const f=metricsFixture(url.pathname.split('/').at(-1));for(const row of f.models)row.segments=empty?[]:[{segment:'additional_bucket',evaluated_users:4}];return response(f);}));
  view();await screen.findByText('No test segments were supplied for this model.');empty=false;fireEvent.change(screen.getByRole('combobox',{name:'Segment analysis model'}),{target:{value:'cf'}});await screen.findByText('additional bucket');expect(document.querySelector('[data-segment="additional_bucket"]')).toHaveTextContent('4');
});
it('shows an empty report with retry rather than hardcoded metrics',async()=>{
  vi.stubGlobal('fetch',mockApi(url=>url.pathname.includes('/metrics/')?response({models:[]}):undefined));view();await screen.findByText('No saved model metrics available.');expect(screen.queryByRole('figure')).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Retry metrics'})).toBeEnabled();
});
it('sanitizes API errors and retries the report independently of readiness',async()=>{
  let fail=true;vi.stubGlobal('fetch',mockApi(url=>{if(url.pathname.endsWith('/metrics/models')&&fail){fail=false;return response({error:{message:'PRIVATE_PATH'}},503);}}));view();await screen.findByRole('alert');expect(document.body.textContent).not.toContain('PRIVATE_PATH');fireEvent.click(screen.getByRole('button',{name:'Try again'}));await ready();expect(fetch.mock.calls.filter(([u])=>u.endsWith('/health/ready'))).toHaveLength(1);
});
it('retries segment errors without refetching the comparison report',async()=>{
  let fail=true;vi.stubGlobal('fetch',mockApi(url=>{if(url.pathname.endsWith('/models/hybrid')&&fail){fail=false;return response({},500);}}));view();await screen.findByText('Segment metrics couldn’t load.');fireEvent.click(screen.getByRole('button',{name:'Try again'}));await ready();expect(fetch.mock.calls.filter(([u])=>u.endsWith('/metrics/models'))).toHaveLength(1);
});
it('ignores a late model-detail response after segment selection changes',async()=>{
  let finish,signal;vi.stubGlobal('fetch',mockApi((url,options)=>{if(url.pathname.endsWith('/models/cf')){signal=options.signal;return new Promise(resolve=>{finish=()=>resolve(response(metricsFixture('cf')));});}}));view();await ready();
  fireEvent.change(screen.getByRole('combobox',{name:'Segment analysis model'}),{target:{value:'cf'}});await waitFor(()=>expect(finish).toBeTypeOf('function'));fireEvent.change(screen.getByRole('combobox',{name:'Segment analysis model'}),{target:{value:'content'}});await screen.findByRole('table',{name:/Content-based — Test segment/});expect(signal.aborted).toBe(true);await act(async()=>finish());expect(screen.queryByRole('table',{name:/Collaborative filtering — Test segment/})).not.toBeInTheDocument();
});
it('provides labeled chart navigation, equivalent tables and required retrospective caveats',async()=>{
  view();await ready();expect(document.querySelectorAll('svg[tabindex="0"]')).toHaveLength(3);expect(document.querySelectorAll('svg[aria-label*="arrow keys"]')).toHaveLength(3);
  expect(screen.getByRole('region',{name:'Scrollable segment metrics'})).toHaveAttribute('tabindex','0');expect(screen.getByText('Synthetic saved limitation from the API.')).toBeInTheDocument();expect(document.body.textContent).toMatch(/five-core selection uses future activity/);expect(document.body.textContent).toMatch(/metadata may postdate/);expect(document.body.textContent).toMatch(/counts must not be added/);
});

it('does not infer a missing default model or invent missing report context',async()=>{
  vi.stubGlobal('fetch',mockApi(url=>{
    if(!url.pathname.includes('/metrics/'))return;
    const f=metricsFixture(url.pathname.match(/\/models\/([^/]+)$/)?.[1]);delete f.default_model;delete f.candidate_products;delete f.evaluation;delete f.relevance;return response(f);
  }));
  view();await screen.findByText('Default model not supplied');expect(document.querySelector('.insight-card-grid')).toHaveTextContent('Not reported');expect(document.querySelector('.evaluation-context')).toHaveTextContent('Not supplied');expect(screen.queryByText('Hybrid is the selected default')).not.toBeInTheDocument();
});
