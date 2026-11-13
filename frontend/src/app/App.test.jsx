import { act,fireEvent,render,screen,waitFor,within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter,useLocation,useNavigate } from 'react-router';
import { beforeEach,describe,expect,it,vi } from 'vitest';
import { App } from './App.jsx';
import { detail,mockCatalog,page,products,response,similar } from '../test/fixtures.js';

function BrowserTools() {
  const location=useLocation(),navigate=useNavigate();
  return <div><output data-testid="location">{location.pathname+location.search}</output>
    <button onClick={()=>navigate(-1)}>Browser back</button><button onClick={()=>navigate(1)}>Browser forward</button>
    <button onClick={()=>navigate('/products/'+products[4].product_id)}>Open another product</button></div>;
}
function renderApp(path='/discover') {
  return render(<MemoryRouter initialEntries={[path]}><App/><BrowserTools/></MemoryRouter>);
}
function listRequests() { return fetch.mock.calls.filter(([raw])=>new URL(raw).pathname.endsWith('/products')); }
function locationParams() { return new URL('http://local'+screen.getByTestId('location').textContent).searchParams; }
async function readyCatalog() { await screen.findByRole('heading',{name:products[0].title,exact:true}); }
beforeEach(()=>vi.stubGlobal('fetch',mockCatalog(vi)));

describe('server catalog browsing',()=>{
  it('loads 24 real response records with API totals and no fabricated commerce fields',async()=>{
    renderApp();await readyCatalog();
    expect(document.querySelectorAll('.product-card')).toHaveLength(24);
    expect(screen.getByText('of 50 products')).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Previous'})).toBeDisabled();
    expect(screen.getByRole('button',{name:'Next'})).toBeEnabled();
    expect(document.querySelector('img')).toBeNull();
    expect(document.body.textContent).not.toMatch(/\$\d|in stock|confidence|purchase probability/i);
    expect(locationParams().get('page')).toBe('1');
    expect(listRequests().every(([u])=>new URL(u).searchParams.get('page_size')==='24')).toBe(true);
  });
  it('uses a 300ms debounce and puts search into the URL with page reset',async()=>{
    renderApp('/discover?page=2');await screen.findByRole('heading',{name:products[24].title});
    vi.useFakeTimers();
    try {
      const previous=listRequests().length;
      fireEvent.change(screen.getByRole('searchbox'),{target:{value:'ZX-42'}});
      await act(async()=>{vi.advanceTimersByTime(299);});
      expect(listRequests()).toHaveLength(previous);
      await act(async()=>{vi.advanceTimersByTime(1);});
      expect(locationParams().get('q')).toBe('ZX-42');expect(locationParams().get('page')).toBe('1');
      expect(listRequests()).toHaveLength(previous+1);
      expect(screen.getByRole('heading',{name:products[0].title})).toBeInTheDocument();
    } finally {vi.useRealTimers();}
  });
  it('loads initial search/category/page from a shared URL',async()=>{
    renderApp('/discover?q=synthetic&category=Screen+Protectors&page=2');
    await screen.findByRole('heading',{name:products[49].title});
    expect(screen.getByRole('searchbox')).toHaveValue('synthetic');
    expect(screen.getByRole('button',{name:'Screen Protectors',exact:true})).toHaveAttribute('aria-pressed','true');
    expect(document.querySelectorAll('.product-card')).toHaveLength(1);
    expect(document.querySelector('.loaded-count')).toHaveTextContent('25–25 of 25 products');
  });
  it('filters with verified backend category values and resets page one',async()=>{
    const user=userEvent.setup();renderApp('/discover?page=2');
    await screen.findByRole('heading',{name:products[24].title});
    await user.click(screen.getByRole('button',{name:'Screen Protectors',exact:true}));
    await screen.findByRole('heading',{name:products[1].title});
    expect(locationParams().get('category')).toBe('Screen Protectors');expect(locationParams().get('page')).toBe('1');
    expect(screen.getByText('of 25 products')).toBeInTheDocument();
    expect(new URL(listRequests().at(-1)[0]).searchParams.get('category')).toBe('Screen Protectors');
  });
  it('paginates next/previous and disables next on the actual last page',async()=>{
    const user=userEvent.setup();renderApp();await readyCatalog();
    await user.click(screen.getByRole('button',{name:'Next'}));await screen.findByRole('heading',{name:products[24].title});
    expect(locationParams().get('page')).toBe('2');
    await user.click(screen.getByRole('button',{name:'Next'}));await screen.findByRole('heading',{name:products[48].title});
    expect(document.querySelectorAll('.product-card')).toHaveLength(2);
    expect(screen.getByRole('button',{name:'Next'})).toBeDisabled();
    await user.click(screen.getByRole('button',{name:'Previous'}));await screen.findByRole('heading',{name:products[24].title});
  });
  it('restores URL filters and search with browser Back/Forward',async()=>{
    const user=userEvent.setup();renderApp('/discover?q=synthetic&page=1');await readyCatalog();
    await user.click(screen.getByRole('button',{name:'Next'}));await screen.findByRole('heading',{name:products[25].title});
    await user.click(screen.getByRole('button',{name:'Screen Protectors',exact:true}));await screen.findByRole('heading',{name:products[1].title});
    await user.click(screen.getByRole('button',{name:'Browser back'}));await screen.findByRole('heading',{name:products[25].title});
    expect(locationParams().has('category')).toBe(false);expect(screen.getByRole('searchbox')).toHaveValue('synthetic');
    await user.click(screen.getByRole('button',{name:'Browser forward'}));await screen.findByRole('heading',{name:products[1].title});
    expect(locationParams().get('category')).toBe('Screen Protectors');
  });
  it('clears combined filters and shows a truthful empty result',async()=>{
    const user=userEvent.setup();renderApp('/discover?q=NO_MATCH&category=Screen+Protectors&page=1');
    expect(await screen.findByRole('heading',{name:'No products found.'})).toBeInTheDocument();
    expect(document.querySelectorAll('.product-card')).toHaveLength(0);
    await user.click(screen.getByRole('button',{name:'Clear filters',exact:true}));await readyCatalog();
    expect(locationParams().has('q')).toBe(false);expect(locationParams().has('category')).toBe(false);
  });
  it('recovers an out-of-range page without inventing result ranges',async()=>{
    const user=userEvent.setup();renderApp('/discover?page=999');
    expect(await screen.findByRole('heading',{name:'This page is outside the collection.'})).toBeInTheDocument();
    expect(screen.queryByRole('navigation',{name:'Catalog pagination'})).not.toBeInTheDocument();
    await user.click(screen.getByRole('button',{name:'Go to first page'}));await readyCatalog();
  });
  it('normalizes invalid pages and explicitly clears unknown featured categories',async()=>{
    renderApp('/discover?category=UNVERIFIED&page=-1');await readyCatalog();
    expect(locationParams().get('page')).toBe('1');expect(locationParams().has('category')).toBe(false);
    expect(screen.getByText(/unrecognized featured-category/)).toBeInTheDocument();
  });
  it('cancels and ignores an outdated search even when its transport ignores abort',async()=>{
    const base=mockCatalog(vi);let finishSlow,slowSignal;
    const slow={...products[0],title:'Slow synthetic result'};const fast={...products[3],title:'Fast synthetic result'};
    vi.stubGlobal('fetch',vi.fn((raw,options)=>{
      const q=new URL(raw).searchParams.get('q');
      if(q==='slow'){slowSignal=options.signal;return new Promise(resolve=>{finishSlow=()=>resolve(response(page([slow],1)));});}
      if(q==='fast')return Promise.resolve(response(page([fast],1)));
      return base(raw,options);
    }));
    renderApp();await readyCatalog();
    fireEvent.change(screen.getByRole('searchbox'),{target:{value:'slow'}});
    await waitFor(()=>expect(finishSlow).toBeTypeOf('function'));
    fireEvent.change(screen.getByRole('searchbox'),{target:{value:'fast'}});
    expect(slowSignal.aborted).toBe(true);
    await screen.findByRole('heading',{name:fast.title});
    await act(async()=>{finishSlow();});
    expect(screen.queryByRole('heading',{name:slow.title})).not.toBeInTheDocument();
    expect(screen.getByRole('heading',{name:fast.title})).toBeInTheDocument();
  });
  it('retains accessible missing-title and browse-only states',async()=>{
    renderApp();await readyCatalog();expect(screen.getByRole('heading',{name:'Title unavailable'})).toBeInTheDocument();
    expect(screen.getByText('Browse-only item')).toBeInTheDocument();
  });
  it('provides readiness retry without exposing internal exception details',async()=>{
    const base=mockCatalog(vi);let fail=true;
    vi.stubGlobal('fetch',vi.fn((raw,options)=>{if(fail){fail=false;return Promise.reject(new TypeError('PRIVATE_PATH'));}return base(raw,options);}));
    renderApp();expect(await screen.findByRole('alert')).not.toHaveTextContent('PRIVATE_PATH');
    fireEvent.click(screen.getByRole('button',{name:'Try again'}));await readyCatalog();
  });
  it('retries a catalog failure separately from readiness',async()=>{
    const base=mockCatalog(vi);let fail=true;
    vi.stubGlobal('fetch',vi.fn((raw,options)=>{if(new URL(raw).pathname.endsWith('/products')&&fail){fail=false;return Promise.resolve(response({},503));}return base(raw,options);}));
    renderApp();await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:'Try again'}));await readyCatalog();
    expect(fetch.mock.calls.filter(([u])=>u.endsWith('/health/ready'))).toHaveLength(1);
  });
  it('aborts loading on unmount and provides responsive skeleton markup',()=>{
    const signals=[];vi.stubGlobal('fetch',vi.fn((url,options)=>{signals.push(options.signal);return new Promise(()=>{});}));
    const app=renderApp();expect(screen.getByRole('status',{name:'Loading products'})).toHaveClass('product-grid');
    app.unmount();expect(signals[0].aborted).toBe(true);
  });
  it('times out instead of waiting indefinitely',async()=>{
    vi.useFakeTimers();
    try {
      vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})));renderApp();
      await act(async()=>{vi.advanceTimersByTime(10001);});
      expect(screen.getByRole('alert')).toHaveTextContent('took too long');
    } finally {vi.useRealTimers();}
  });
});

describe('product detail and similarity integration',()=>{
  it('loads a direct URL beyond the old preview and preserves actual training labels',async()=>{
    renderApp('/products/'+products[35].product_id);
    expect(await screen.findByRole('heading',{level:1,name:products[35].title})).toBeInTheDocument();
    const stats=screen.getByLabelText('Historical training statistics');
    expect(within(stats).getByText('17')).toBeInTheDocument();expect(within(stats).getByText('4.25 / 5')).toBeInTheDocument();
    expect(screen.getByText(/not current marketplace reviews/)).toBeInTheDocument();
    expect(listRequests()).toHaveLength(0);
    expect(await screen.findByText(/related products, ordered/)).toBeInTheDocument();
  });
  it('preserves catalog filters when opening details and returning to results',async()=>{
    const user=userEvent.setup();renderApp('/discover?q=synthetic&page=2');await screen.findByRole('heading',{name:products[25].title});
    await user.click(screen.getByRole('link',{name:products[25].title,exact:true}));
    await screen.findByRole('heading',{level:1,name:products[25].title});
    expect(screen.getByRole('link',{name:'Back to results'})).toHaveAttribute('href','/discover?q=synthetic&page=2');
    await user.click(screen.getByRole('link',{name:'Back to results'}));await screen.findByRole('heading',{name:products[25].title});
    expect(screen.getByRole('searchbox')).toHaveValue('synthetic');expect(locationParams().get('page')).toBe('2');
  });
  it('does not request similarity for outside-catalog products and shows missing statistics honestly',async()=>{
    renderApp('/products/'+products[1].product_id);await screen.findByRole('heading',{level:1,name:products[1].title});
    expect(screen.getAllByText('Not available')).toHaveLength(2);
    expect(screen.getByText(/outside the frozen recommendation catalog/)).toBeInTheDocument();
    expect(fetch.mock.calls.every(([u])=>!u.endsWith('/similar'))).toBe(true);
  });
  it('handles missing titles, absent categories and zero similarity results',async()=>{
    renderApp('/products/'+products[2].product_id);
    expect(await screen.findByRole('heading',{level:1,name:'Title unavailable'})).toBeInTheDocument();
    expect(screen.getByText('Category unavailable')).toBeInTheDocument();
    expect(screen.getByText('No category hierarchy provided')).toBeInTheDocument();
    expect(await screen.findByRole('heading',{name:'No similar products found.'})).toBeInTheDocument();
  });
  it('distinguishes a product 404 from a backend failure',async()=>{
    renderApp('/products/UNKNOWN');expect(await screen.findByRole('heading',{name:'Product not found.'})).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('PRIVATE_INTERNAL_DETAIL');
  });
  it('retries failed product lookups',async()=>{
    const base=mockCatalog(vi);let fail=true;
    vi.stubGlobal('fetch',vi.fn((raw,options)=>{if(raw.endsWith('/products/'+products[0].product_id)&&fail){fail=false;return Promise.resolve(response({},503));}return base(raw,options);}));
    renderApp('/products/'+products[0].product_id);await screen.findByRole('alert');
    expect(screen.getByRole('heading',{level:1,name:'This product couldn’t load.'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'Try again'}));await screen.findByRole('heading',{level:1,name:products[0].title});
  });
  it('retries similarity errors without losing or refetching the product detail',async()=>{
    const base=mockCatalog(vi);let fail=true;
    vi.stubGlobal('fetch',vi.fn((raw,options)=>{if(raw.endsWith('/similar')&&fail){fail=false;return Promise.resolve(response({},503));}return base(raw,options);}));
    renderApp('/products/'+products[0].product_id);await screen.findByRole('alert');
    expect(screen.getByRole('heading',{level:1,name:products[0].title})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'Try again'}));await screen.findByText(/related products, ordered/);
    expect(fetch.mock.calls.filter(([u])=>u.endsWith('/products/'+products[0].product_id))).toHaveLength(1);
  });
  it('handles an eligibility/similarity 409 response as information',async()=>{
    const base=mockCatalog(vi);
    vi.stubGlobal('fetch',vi.fn((raw,options)=>raw.endsWith('/similar')?Promise.resolve(response({},409)):base(raw,options)));
    renderApp('/products/'+products[0].product_id);await screen.findByText(/outside the frozen recommendation catalog/);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('preserves backend ordering and never turns similarity scores into confidence',async()=>{
    renderApp('/products/'+products[0].product_id);await screen.findByText(/related products, ordered/);
    expect([...document.querySelectorAll('.similar-grid h3')].map(x=>x.textContent)).toEqual([products[3].title,products[4].title]);
    expect(document.body.textContent).not.toMatch(/80%|70%|confidence/i);
  });
  it('cancels old similarity work when the product route changes',async()=>{
    const base=mockCatalog(vi);let oldSignal,finish;
    vi.stubGlobal('fetch',vi.fn((raw,options)=>{
      if(raw.endsWith('/'+products[0].product_id+'/similar')){oldSignal=options.signal;return new Promise(resolve=>{finish=()=>resolve(response(similar(products[0].product_id)));});}
      return base(raw,options);
    }));
    renderApp('/products/'+products[0].product_id);await waitFor(()=>expect(finish).toBeTypeOf('function'));
    fireEvent.click(screen.getByRole('button',{name:'Open another product'}));
    await screen.findByRole('heading',{level:1,name:products[4].title});expect(oldSignal.aborted).toBe(true);
    await act(async()=>{finish();});
    expect(screen.getByRole('heading',{level:1,name:products[4].title})).toBeInTheDocument();
  });
});

describe('unchanged visual shell and future-stage boundaries',()=>{
  it('moves keyboard focus into the new page after internal route navigation',async()=>{
    const user=userEvent.setup();renderApp();await readyCatalog();
    await user.click(screen.getByRole('link',{name:products[0].title,exact:true}));
    await screen.findByRole('heading',{level:1,name:products[0].title});expect(document.getElementById('main-content')).toHaveFocus();
  });
  it('preserves search focus while only URL query parameters change',async()=>{
    const user=userEvent.setup();renderApp();await readyCatalog();const input=screen.getByRole('searchbox');await user.type(input,'ZX-42');
    await waitFor(()=>expect(document.querySelectorAll('.product-card')).toHaveLength(1));expect(input).toHaveFocus();
  });
  it('connects profile selection and the historical Insights route without fabricated empty-report metrics',async()=>{
    const user=userEvent.setup();renderApp('/for-you');
    expect(screen.getByRole('heading',{name:'A little more you.'})).toBeInTheDocument();
    await screen.findByRole('combobox',{name:'Demo profile'});
    expect(screen.getByRole('button',{name:'Create a new demo profile'})).toBeEnabled();
    await user.click(within(screen.getByRole('navigation',{name:'Main navigation'})).getByRole('link',{name:'AI Insights'}));
    expect(await screen.findByText('Historical Evaluation')).toBeInTheDocument();
    expect(await screen.findByText('No saved model metrics available.')).toBeInTheDocument();
    expect(fetch.mock.calls.every(([u])=>u.endsWith('/health/ready') || u.endsWith('/demo/profiles') || u.endsWith('/metrics/models'))).toBe(true);
  });
  it('retains skip links, active navigation and mobile navigation controls',async()=>{
    const user=userEvent.setup();renderApp('/for-you');
    const nav=screen.getByRole('navigation',{name:'Main navigation'});
    expect(within(nav).getByRole('link',{name:'For You'})).toHaveAttribute('aria-current','page');
    expect(screen.getByRole('link',{name:'Skip to content'})).toHaveAttribute('href','#main-content');
    expect(screen.getByRole('navigation',{name:'Mobile navigation'})).toBeInTheDocument();
    await user.click(within(nav).getByRole('link',{name:'Discover'}));await readyCatalog();
    expect(document.title).toBe('Discover · SmartShop AI');
  });
  it('recovers unknown frontend routes without inventing product data',()=>{
    renderApp('/unknown-route');expect(screen.getByRole('heading',{name:'Let’s find your way back.'})).toBeInTheDocument();
    expect(screen.getByRole('link',{name:'Explore the catalog'})).toBeInTheDocument();
  });
});
