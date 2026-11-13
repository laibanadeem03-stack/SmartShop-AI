import { act,fireEvent,render,screen,waitFor,within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach,expect,it,vi } from 'vitest';
import { App } from '../../app/App.jsx';
import { PROFILE_KEY } from './ProfileProvider.jsx';
import { products,response } from '../../test/fixtures.js';
import { explanation,mockRecommendations,newUser,profiles,recommendations } from '../../test/recommendationFixtures.js';

const renderPage=()=>render(<MemoryRouter initialEntries={['/for-you']}><App/></MemoryRouter>);
async function selectProfile(value='demo_1') { const control=await screen.findByRole('combobox',{name:'Demo profile'});fireEvent.change(control,{target:{value}}); }
async function loaded() { await screen.findByText('Served by Hybrid'); }
const requests=part=>fetch.mock.calls.filter(([raw])=>raw.includes(part));
beforeEach(()=>vi.stubGlobal('fetch',mockRecommendations(vi)));

it('shows all twelve public profiles without automatically creating or recommending',async()=>{
  renderPage();const select=await screen.findByRole('combobox',{name:'Demo profile'});
  expect(within(select).getAllByRole('option')).toHaveLength(13);
  expect(screen.getByText(/12 anonymous historical profiles/)).toBeInTheDocument();
  expect(requests('/demo/users')).toHaveLength(0);expect(requests('/recommendations?')).toHaveLength(0);
  expect(screen.getByRole('combobox',{name:'Recommendation model'})).toHaveValue('hybrid');
});
it('preserves backend ordering, ranks, sources, metadata and actual counts',async()=>{
  renderPage();await selectProfile();await loaded();
  expect([...document.querySelectorAll('.recommendation-grid h3')].map(el=>el.textContent)).toEqual([products[4].title,products[0].title]);
  expect([...document.querySelectorAll('.recommendation-evidence')].map(el=>[el.dataset.rank,el.dataset.source])).toEqual([['1','hybrid_both'],['2','hybrid_both']]);
  expect(screen.getByText('2 recommendations · 2 personalized · 0 popularity / fallback')).toBeInTheDocument();
  expect(document.querySelectorAll('.recommendation-grid img')).toHaveLength(0);
});
it('switches all four exact backend model values',async()=>{
  renderPage();await selectProfile();await loaded();
  for(const [model,label] of [['content','Content-based'],['cf','Collaborative'],['count','Count popularity'],['hybrid','Hybrid']]) {
    fireEvent.change(screen.getByRole('combobox',{name:'Recommendation model'}),{target:{value:model}});
    await screen.findByText('Served by '+label);
    expect(new URL(requests('/recommendations?').at(-1)[0]).searchParams.get('model')).toBe(model);
  }
});
it('persists only public alias and type and restores a historical selection',async()=>{
  localStorage.setItem(PROFILE_KEY,JSON.stringify(profiles[2]));renderPage();await loaded();
  await selectProfile('demo_2');await loaded();
  expect(JSON.parse(localStorage.getItem(PROFILE_KEY))).toEqual({public_user_id:'demo_2',profile_type:'dataset_backed'});
  expect(localStorage.length).toBe(1);
  expect(localStorage.getItem(PROFILE_KEY)).not.toMatch(/batch|score|label|reason/);
});
it('ignores malformed persisted profiles',async()=>{
  localStorage.setItem(PROFILE_KEY,'{"public_user_id":"../private","profile_type":"dataset_backed"}');renderPage();
  await screen.findByRole('combobox',{name:'Demo profile'});expect(requests('/recommendations?')).toHaveLength(0);
});
it('creates a cold-start profile only on a click and displays the actual served model',async()=>{
  const user=userEvent.setup();renderPage();await screen.findByRole('combobox',{name:'Demo profile'});
  await user.click(screen.getByRole('button',{name:'Create a new demo profile'}));
  await screen.findByText('Served by Count popularity');
  expect(screen.getByText(/Frozen count popularity is served instead of Hybrid/)).toBeInTheDocument();
  expect(screen.getByText('2 recommendations · 0 personalized · 2 popularity / fallback')).toBeInTheDocument();
  const [,options]=requests('/demo/users')[0];expect(options.method).toBe('POST');expect(options.body).toBe('{}');
  expect(JSON.parse(localStorage.getItem(PROFILE_KEY))).toEqual({public_user_id:newUser.public_user_id,profile_type:'new_demo'});
});
it('restores a new local profile without another POST',async()=>{
  localStorage.setItem(PROFILE_KEY,JSON.stringify(newUser));renderPage();await screen.findByText('Served by Count popularity');
  expect(requests('/demo/users')).toHaveLength(0);
  expect(screen.getByRole('combobox',{name:'Demo profile'})).toHaveValue(newUser.public_user_id);
});
it('blocks duplicate profile creation while a click is pending',async()=>{
  let finish;vi.stubGlobal('fetch',mockRecommendations(vi,(url)=>url.pathname.endsWith('/demo/users')?new Promise(resolve=>{finish=()=>resolve(response(newUser,201));}):undefined));
  renderPage();await screen.findByRole('combobox',{name:'Demo profile'});const button=screen.getByRole('button',{name:'Create a new demo profile'});
  fireEvent.click(button);fireEvent.click(button);expect(requests('/demo/users')).toHaveLength(1);
  await act(async()=>finish());await screen.findByText('Served by Count popularity');
});
it('shows sanitized profile creation failures without automatic retries',async()=>{
  vi.stubGlobal('fetch',mockRecommendations(vi,url=>url.pathname.endsWith('/demo/users')?response({error:{code:'LOCAL_USER_LIMIT',message:'PRIVATE_PATH'}},409):undefined));
  renderPage();await screen.findByRole('combobox',{name:'Demo profile'});fireEvent.click(screen.getByRole('button',{name:'Create a new demo profile'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('local demo-profile limit');expect(document.body.textContent).not.toContain('PRIVATE_PATH');expect(requests('/demo/users')).toHaveLength(1);
});
it('shows actual reason, supporting products, shared features and fusion evidence',async()=>{
  renderPage();await selectProfile();await loaded();fireEvent.click(screen.getAllByRole('button',{name:/Why this recommendation/})[0]);
  const dialog=await screen.findByRole('dialog');await within(dialog).findByText('Synthetic verified reason from the API.');
  expect(within(dialog).getByRole('link',{name:products[3].title})).toHaveAttribute('href','/products/'+products[3].product_id);
  expect(within(dialog).getByText('zx-42')).toBeInTheDocument();expect(within(dialog).getByText('#3')).toBeInTheDocument();expect(within(dialog).getByText('#7')).toBeInTheDocument();
  expect(dialog.querySelector('details')).not.toHaveAttribute('open');
  fireEvent.click(within(dialog).getByText('Technical details'));expect(within(dialog).getByText('normalized_weighted_rrf')).toBeInTheDocument();expect(within(dialog).getByText('0.011')).toBeInTheDocument();
  expect(localStorage.getItem(PROFILE_KEY)).not.toMatch(/batch|zx-42|score/);
});
it('explains cold-start popularity using real training-count evidence',async()=>{
  localStorage.setItem(PROFILE_KEY,JSON.stringify(newUser));renderPage();await screen.findByText('Served by Count popularity');
  fireEvent.click(screen.getAllByRole('button',{name:/Why this recommendation/})[0]);const dialog=await screen.findByRole('dialog');
  await within(dialog).findByText('A popularity starting point');expect(dialog.querySelector('.evidence-section strong')).toHaveTextContent('57');
  expect(within(dialog).queryByText('Shared content features')).not.toBeInTheDocument();
});
it('traps keyboard focus, handles Escape and restores the trigger',async()=>{
  const user=userEvent.setup();renderPage();await selectProfile();await loaded();const trigger=screen.getAllByRole('button',{name:/Why this recommendation/})[0];
  trigger.focus();await user.click(trigger);const dialog=await screen.findByRole('dialog');await within(dialog).findByText('Synthetic verified reason from the API.');
  const close=within(dialog).getByRole('button',{name:'Close explanation'});expect(close).toHaveFocus();
  await user.tab({shift:true});expect(within(dialog).getByText('Technical details')).toHaveFocus();
  await user.tab();expect(close).toHaveFocus();await user.keyboard('{Escape}');expect(screen.queryByRole('dialog')).not.toBeInTheDocument();expect(trigger).toHaveFocus();expect(document.body.style.overflow).toBe('');
});
it('clears old results immediately and rejects late recommendations across profiles',async()=>{
  let finish,signal;vi.stubGlobal('fetch',mockRecommendations(vi,(url,options)=>url.pathname.includes('/users/demo_1/')?new Promise(resolve=>{signal=options.signal;finish=()=>resolve(response(recommendations('demo_1','hybrid','old',[products[5]])));}):undefined));
  renderPage();await selectProfile();await waitFor(()=>expect(finish).toBeTypeOf('function'));await selectProfile('demo_2');
  expect(signal.aborted).toBe(true);await loaded();await act(async()=>finish());expect(screen.queryByRole('heading',{name:products[5].title})).not.toBeInTheDocument();
});
it('clears an open explanation and rejects late evidence when the model changes',async()=>{
  let finish,signal;vi.stubGlobal('fetch',mockRecommendations(vi,(url,options,batches)=>{
    if(url.pathname.endsWith('/explanation')){signal=options.signal;const parts=url.pathname.split('/');const body=explanation(batches.get(parts.at(-4)),parts.at(-2));return new Promise(resolve=>{finish=()=>resolve(response(body));});}
  }));
  renderPage();await selectProfile();await loaded();fireEvent.click(screen.getAllByRole('button',{name:/Why this recommendation/})[0]);await waitFor(()=>expect(finish).toBeTypeOf('function'));
  fireEvent.change(screen.getByRole('combobox',{name:'Recommendation model'}),{target:{value:'content'}});
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();expect(signal.aborted).toBe(true);await screen.findByText('Served by Content-based');await act(async()=>finish());expect(screen.queryByText('Synthetic verified reason from the API.')).not.toBeInTheDocument();
});
it('refreshes an expired batch and explains the item only in the new batch',async()=>{
  let expired=true;vi.stubGlobal('fetch',mockRecommendations(vi,url=>{if(expired&&url.pathname.endsWith('/explanation')){expired=false;return response({error:{code:'BATCH_NOT_FOUND'}},404);}}));
  renderPage();await selectProfile();await loaded();fireEvent.click(screen.getAllByRole('button',{name:/Why this recommendation/})[0]);
  await screen.findByText('Time for a fresh connection.');fireEvent.click(screen.getByRole('button',{name:'Refresh recommendations'}));await screen.findByText('Synthetic verified reason from the API.');
  expect(requests('/recommendations?')).toHaveLength(2);expect(requests('/explanation')).toHaveLength(2);expect(requests('/explanation')[1][0]).toContain('/batch_2/');
});
it('does not request refreshed evidence if the product is no longer recommended',async()=>{
  let n=0;vi.stubGlobal('fetch',mockRecommendations(vi,url=>{
    if(url.pathname.includes('/users/'))return response(recommendations('demo_1','hybrid','batch_'+(++n),n===1?[products[4]]:[products[0]]));
    if(url.pathname.endsWith('/explanation'))return response({error:{code:'BATCH_NOT_FOUND'}},404);
  }));
  renderPage();await selectProfile();await loaded();fireEvent.click(screen.getByRole('button',{name:/Why this recommendation/}));await screen.findByText('Time for a fresh connection.');
  fireEvent.click(screen.getByRole('button',{name:'Refresh recommendations'}));await screen.findByText('This product is no longer in the refreshed recommendations.');expect(requests('/explanation')).toHaveLength(1);
});
it('recovers an inaccessible persisted profile through explicit selection',async()=>{
  localStorage.setItem(PROFILE_KEY,JSON.stringify({public_user_id:'missing',profile_type:'dataset_backed'}));
  vi.stubGlobal('fetch',mockRecommendations(vi,url=>url.pathname.includes('/users/missing/')?response({error:{code:'USER_NOT_FOUND',message:'PRIVATE_ID'}},404):undefined));
  renderPage();await screen.findByText('This profile is unavailable.');fireEvent.click(screen.getByRole('button',{name:'Choose another profile'}));expect(localStorage.getItem(PROFILE_KEY)).toBeNull();
  await selectProfile();await loaded();expect(document.body.textContent).not.toContain('PRIVATE_ID');
});
it('offers recommendation retry and empty results without inventing picks',async()=>{
  let fail=true;vi.stubGlobal('fetch',mockRecommendations(vi,url=>{
    if(url.pathname.includes('/users/')){if(fail){fail=false;return response({error:{message:'PRIVATE_EXCEPTION'}},500);}return response(recommendations('demo_1','hybrid','empty',[]));}
  }));
  renderPage();await selectProfile();await screen.findByRole('alert');expect(document.body.textContent).not.toContain('PRIVATE_EXCEPTION');fireEvent.click(screen.getByRole('button',{name:'Try again'}));await screen.findByText('No recommendations returned.');expect(document.querySelectorAll('.recommendation-grid article')).toHaveLength(0);
});

it('retries profile listing independently without creating a user',async()=>{
  let fail=true;vi.stubGlobal('fetch',mockRecommendations(vi,url=>{if(url.pathname.endsWith('/demo/profiles')&&fail){fail=false;return response({},503);}}));
  renderPage();await screen.findByText('Profiles couldn’t load.');fireEvent.click(screen.getByRole('button',{name:'Try again'}));await selectProfile();await loaded();expect(requests('/demo/users')).toHaveLength(0);
});
it('cancels a pending explanation when dismissed and ignores its late result',async()=>{
  let finish,signal;vi.stubGlobal('fetch',mockRecommendations(vi,(url,options,batches)=>{
    if(url.pathname.endsWith('/explanation')){signal=options.signal;const parts=url.pathname.split('/');return new Promise(resolve=>{finish=()=>resolve(response(explanation(batches.get(parts.at(-4)),parts.at(-2))));});}
  }));
  renderPage();await selectProfile();await loaded();fireEvent.click(screen.getAllByRole('button',{name:/Why this recommendation/})[0]);await waitFor(()=>expect(finish).toBeTypeOf('function'));
  fireEvent.click(screen.getByRole('button',{name:'Close explanation'}));expect(signal.aborted).toBe(true);await act(async()=>finish());expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
it('retries a failed expiry refresh without reviving old evidence',async()=>{
  let calls=0,expired=true;vi.stubGlobal('fetch',mockRecommendations(vi,url=>{
    if(url.pathname.includes('/users/')&&++calls===2)return response({},503);
    if(url.pathname.endsWith('/explanation')&&expired){expired=false;return response({error:{code:'BATCH_NOT_FOUND'}},404);}
  }));
  renderPage();await selectProfile();await loaded();fireEvent.click(screen.getAllByRole('button',{name:/Why this recommendation/})[0]);await screen.findByText('Time for a fresh connection.');
  fireEvent.click(screen.getByRole('button',{name:'Refresh recommendations'}));const dialog=screen.getByRole('dialog');await within(dialog).findByText('The explanation couldn’t load.');
  fireEvent.click(within(dialog).getByRole('button',{name:'Try explanation again'}));await within(dialog).findByText('Synthetic verified reason from the API.');expect(requests('/recommendations?')).toHaveLength(3);
});
it('uses a fresh request after switching models and ignores an older model response',async()=>{
  let finish,signal;vi.stubGlobal('fetch',mockRecommendations(vi,(url,options)=>{
    if(url.searchParams.get('model')==='cf'){signal=options.signal;return new Promise(resolve=>{finish=()=>resolve(response(recommendations('demo_1','cf','old',[products[5]])));});}
  }));
  renderPage();await selectProfile();await loaded();fireEvent.change(screen.getByRole('combobox',{name:'Recommendation model'}),{target:{value:'cf'}});
  expect(screen.queryByText('Served by Hybrid')).not.toBeInTheDocument();await waitFor(()=>expect(finish).toBeTypeOf('function'));
  fireEvent.change(screen.getByRole('combobox',{name:'Recommendation model'}),{target:{value:'content'}});expect(signal.aborted).toBe(true);await screen.findByText('Served by Content-based');await act(async()=>finish());expect(screen.queryByText('Served by Collaborative')).not.toBeInTheDocument();
});

it('times out profile creation even when its transport ignores abort, without a late selection',async()=>{
  let finish,signal;vi.stubGlobal('fetch',mockRecommendations(vi,(url,options)=>url.pathname.endsWith('/demo/users')?new Promise(resolve=>{signal=options.signal;finish=()=>resolve(response(newUser,201));}):undefined));
  renderPage();await screen.findByRole('combobox',{name:'Demo profile'});vi.useFakeTimers();
  try {
    fireEvent.click(screen.getByRole('button',{name:'Create a new demo profile'}));await act(async()=>vi.advanceTimersByTime(10001));
    expect(screen.getByRole('alert')).toHaveTextContent('It may have completed on the server');expect(signal.aborted).toBe(true);
    await act(async()=>finish());expect(localStorage.getItem(PROFILE_KEY)).toBeNull();expect(requests('/recommendations?')).toHaveLength(0);
  } finally {vi.useRealTimers();}
});

it('restores focus to the replacement explanation trigger after refreshing an expired batch',async()=>{
  const user=userEvent.setup();let expired=true;vi.stubGlobal('fetch',mockRecommendations(vi,url=>{if(expired&&url.pathname.endsWith('/explanation')){expired=false;return response({error:{code:'BATCH_NOT_FOUND'}},404);}}));
  renderPage();await selectProfile();await loaded();await user.click(screen.getAllByRole('button',{name:/Why this recommendation/})[0]);await screen.findByText('Time for a fresh connection.');
  await user.click(screen.getByRole('button',{name:'Refresh recommendations'}));await screen.findByText('Synthetic verified reason from the API.');await user.click(screen.getByRole('button',{name:'Close explanation'}));expect(screen.getAllByRole('button',{name:/Why this recommendation/})[0]).toHaveFocus();
});

it('restores focus to the picks heading when the refreshed product disappeared',async()=>{
  const user=userEvent.setup();let n=0;vi.stubGlobal('fetch',mockRecommendations(vi,url=>{
    if(url.pathname.includes('/users/'))return response(recommendations('demo_1','hybrid','batch_'+(++n),n===1?[products[4]]:[products[0]]));
    if(url.pathname.endsWith('/explanation'))return response({error:{code:'BATCH_NOT_FOUND'}},404);
  }));
  renderPage();await selectProfile();await loaded();await user.click(screen.getByRole('button',{name:/Why this recommendation/}));await screen.findByText('Time for a fresh connection.');
  await user.click(screen.getByRole('button',{name:'Refresh recommendations'}));await screen.findByText('This product is no longer in the refreshed recommendations.');await user.click(screen.getByRole('button',{name:'Close explanation'}));expect(screen.getByRole('heading',{name:'Your next connections.'})).toHaveFocus();
});

it('continues in memory if browser persistence is denied',async()=>{
  const spy=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('Storage disabled');});
  try {renderPage();await selectProfile();await loaded();expect(screen.getByText(/Browser storage is unavailable/)).toBeInTheDocument();expect(localStorage.length).toBe(0);}
  finally {spy.mockRestore();}
});
