import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Layers2, Plus, Sparkles, UserRound } from 'lucide-react';
import { useApiReadiness } from '../../api/ApiReadinessProvider.jsx';
import { useApiResource } from '../../api/useApiResource.js';
import { ApiError } from '../../api/catalog.js';
import { createDemoUser, loadExplanation, loadProfiles, loadRecommendations, MODELS, SOURCES } from '../../api/recommendations.js';
import { ProductCard } from '../../components/products/ProductCard.jsx';
import { Button } from '../../components/ui/Button.jsx';
import { CatalogError, ProductSkeletons } from '../../components/ui/CatalogStates.jsx';
import { ExplanationDialog } from './ExplanationDialog.jsx';
import { useProfile } from './ProfileProvider.jsx';

function Recommendations({ selected, model, onUnavailable }) {
  const [generation, setGeneration] = useState(0);
  const [target, setTarget] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [missing, setMissing] = useState(false);
  const load = useCallback(signal => loadRecommendations(selected.public_user_id, model, signal), [selected.public_user_id,model]);
  const resource = useApiResource(`${selected.public_user_id}:${model}:${generation}`, load);
  const batch = resource.data;
  const item = batch?.items.find(item => item.product.product_id === target?.product_id);
  const explain = useCallback(signal => loadExplanation(batch.batch_id, item, batch.model, signal), [batch,item]);
  const explanation = useApiResource(`${batch?.batch_id}:${target?.product_id}`, explain, !!item && !refreshing);
  useEffect(() => {
    if (!refreshing || resource.status === 'loading') return;
    if (resource.status === 'ready') { setMissing(!item); setRefreshing(false); }
    else if (resource.status === 'error') setRefreshing(false);
  }, [refreshing,resource.status,item]);
  function refresh() { setMissing(false); setRefreshing(true); setGeneration(n => n+1); }
  function open(product) { setMissing(false); setTarget(product); }
  const unavailable = resource.error?.code === 'USER_NOT_FOUND';
  // Refresh errors stay in the dialog and can be retried without reviving old evidence.
  const dialogResource = resource.status === 'error' ? { ...resource, retry: refresh } : explanation;
  return <section className="recommendation-results" aria-labelledby="picks-heading" aria-busy={resource.status === 'loading'} data-model={batch?.model || ''} data-profile={selected.public_user_id}>
    <div className="picks-heading"><div><span className="section-kicker">A DIFFERENT WAY TO DISCOVER</span><h2 id="picks-heading" tabIndex={-1}>Your next connections.</h2></div><Sparkles size={24} aria-hidden="true" /></div>
    {resource.status === 'loading' && <ProductSkeletons count={6} label="Loading recommendations" />}
    {resource.status === 'error' && (unavailable ? <div className="empty-state" role="alert"><h2>This profile is unavailable.</h2><p>{resource.error.message}</p><Button onClick={onUnavailable} variant="secondary">Choose another profile</Button></div> : <CatalogError error={resource.error} retry={resource.retry} title="Your recommendations couldn’t load." />)}
    {batch && <>
      <div className="recommendation-summary" role="status"><div><span className="served-model">Served by {MODELS[batch.model]}</span><p>{batch.returned_count} recommendations · {batch.personalized_count} personalized · {batch.fallback_count} popularity / fallback</p></div><span className="snapshot-tag">Training snapshot</span></div>
      {batch.cold_start && <div className="cold-start-note"><UserRound size={22} aria-hidden="true" /><div><strong>A fresh start, grounded in popularity.</strong><p>This profile has no training history. Frozen count popularity is served{batch.requested_model !== 'count' ? ` instead of ${MODELS[batch.requested_model]}` : ''}. Browsing does not teach the model your preferences.</p></div></div>}
      {!batch.cold_start && model === 'hybrid' && <p className="ranking-note">Hybrid starts with equal collaborative and content weights; available signals are normalized per profile before popularity backfill.</p>}
      {batch.items.length ? <div className="product-grid recommendation-grid">{batch.items.map(item => <ProductCard key={item.product.product_id} product={item.product} index={item.rank-1}>
        <div className="recommendation-evidence" data-product-id={item.product.product_id} data-rank={item.rank} data-source={item.source}><div className="recommendation-labels"><span className="rank-label">#{item.rank}</span><span className="source-label">{SOURCES[item.source]}</span></div><button type="button" className="why-button" onClick={() => open(item.product)} aria-label={`Why this recommendation? ${item.product.title_available ? item.product.title : 'Title unavailable'}`}>Why this recommendation? <ArrowUpRight size={15} aria-hidden="true" /></button></div>
      </ProductCard>)}</div> : <div className="empty-state"><h3>No recommendations returned.</h3><p>There are no available picks for this profile and model. Try another model or profile.</p><Button variant="secondary" onClick={resource.retry}>Refresh picks</Button></div>}
    </>}
    {target && <ExplanationDialog product={target} resource={dialogResource} refreshing={refreshing} missing={missing} onClose={() => { setTarget(null); setMissing(false); setRefreshing(false); }} onRefresh={refresh} />}
  </section>;
}

export function ForYouPage() {
  const readiness = useApiReadiness();
  const profiles = useApiResource('demo-profiles', loadProfiles, readiness.status === 'ready');
  const { selected, select, storageUnavailable } = useProfile();
  const [model, setModel] = useState('hybrid');
  const [creation, setCreation] = useState({ status: 'idle', error: null });
  const pending = useRef(null);
  useEffect(() => () => { const controller = pending.current; pending.current = null; controller?.abort(); }, []);
  async function create() {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller;
    setCreation({ status: 'loading', error: null });
    const timeout = setTimeout(() => {
      if (pending.current !== controller) return;
      controller.abort(); pending.current = null;
      setCreation({ status: 'error', error: new ApiError('TIMEOUT','Profile creation timed out. It may have completed on the server; retrying creates a separate profile.') });
    }, 10000);
    controller.signal.addEventListener('abort', () => clearTimeout(timeout), { once: true });
    try {
      const user = await createDemoUser(controller.signal);
      if (!controller.signal.aborted) { select(user); setCreation({ status: 'idle', error: null }); }
    } catch (error) {
      if (pending.current === controller) setCreation({ status: 'error', error: controller.signal.aborted ? new ApiError('TIMEOUT','Profile creation timed out. It may have completed on the server; retrying creates a separate profile.') : error });
    } finally { clearTimeout(timeout); if (pending.current === controller) pending.current = null; }
  }
  const selectedRecord = profiles.data?.items.find(p => p.public_user_id === selected?.public_user_id);
  return <div className="page-width for-you-page">
    <header className="for-you-heading"><span className="section-kicker">PERSONAL DISCOVERY</span><h1>A little more you.</h1><p>Explore recommendations with a reason behind every connection.</p></header>
    {readiness.status === 'error' ? <CatalogError error={readiness.error} retry={readiness.retry} /> : <div className="personal-discovery-layout">
      <aside className="profile-panel" aria-labelledby="profile-heading"><span className="profile-avatar"><UserRound size={26} aria-hidden="true" /></span><h2 id="profile-heading">Your discovery profile</h2><p>Explore an anonymous historical profile, or start with a clean slate.</p>
        {profiles.status === 'loading' || readiness.status === 'loading' ? <p role="status">Loading demo profiles…</p> : profiles.status === 'error' ? <CatalogError error={profiles.error} retry={profiles.retry} title="Profiles couldn’t load." /> : <>
          <label htmlFor="profile-select">Demo profile</label><select id="profile-select" value={selected?.public_user_id || ''} disabled={creation.status === 'loading'} onChange={event => { const profile = profiles.data.items.find(p => p.public_user_id === event.target.value); select(profile || (selected?.profile_type === 'new_demo' && event.target.value === selected.public_user_id ? selected : null)); }}>
            <option value="">Choose a profile</option>{profiles.data?.items.map(p => <option key={p.public_user_id} value={p.public_user_id}>{p.label} · {p.activity}</option>)}
            {selected && !selectedRecord && <option value={selected.public_user_id}>{selected.profile_type === 'new_demo' ? 'New demo user · no training history' : 'Previously selected profile'}</option>}
          </select>
          <p className="field-hint">{profiles.data?.total} anonymous historical profiles. Private dataset identifiers are never displayed.</p>
        </>}
        <Button variant="secondary" onClick={create} disabled={readiness.status !== 'ready' || creation.status === 'loading'}><Plus size={16} aria-hidden="true" />{creation.status === 'loading' ? 'Creating profile…' : 'Create a new demo profile'}</Button>
        {creation.error && <p className="inline-error" role="alert">{creation.error.message}</p>}
        {storageUnavailable && <p role="status" className="field-hint">Browser storage is unavailable. This selection will last for this visit only.</p>}
        <div className="model-control"><label htmlFor="model-select">Recommendation model</label><select id="model-select" value={model} onChange={event => setModel(event.target.value)}>{Object.entries(MODELS).map(([value,label]) => <option key={value} value={value}>{label}{value === 'hybrid' ? ' · default' : ''}</option>)}</select></div>
        <div className="profile-note"><Layers2 size={18} aria-hidden="true" /><div><strong>Frozen models. Real evidence.</strong><span>Historical profiles use training ratings only. New profiles start with popularity.</span></div></div>
        <p className="field-hint">Only the selected public profile alias and type are saved in this browser. No rating submission or preference learning is enabled.</p>
      </aside>
      {selected && readiness.status === 'ready' ? <Recommendations key={`${selected.public_user_id}:${model}`} selected={selected} model={model} onUnavailable={() => { select(null); document.getElementById('profile-select')?.focus(); }} /> : <section className="choose-profile-state"><span className="empty-personalized-art" aria-hidden="true"><div><Sparkles size={42} strokeWidth={1.2} /></div></span><span className="section-kicker">MADE FOR YOUR PERSPECTIVE</span><h2>Your next connection<br />starts here.</h2><p>Choose a historical demo profile to explore personalized picks, or create a new profile for a popularity-based starting point.</p><span className="quiet-label">Every connection has a reason <ArrowUpRight size={14} aria-hidden="true" /></span></section>}
    </div>}
    <p className="personal-discovery-caveat">A historical discovery demo, not live shopping advice. Models and histories are frozen; metadata may postdate the original training cutoff.</p>
  </div>;
}
