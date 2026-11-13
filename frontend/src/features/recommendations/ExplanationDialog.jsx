import { useEffect, useRef } from 'react';
import { Link } from 'react-router';
import { X } from 'lucide-react';
import { MODELS, SOURCES } from '../../api/recommendations.js';
import { Button } from '../../components/ui/Button.jsx';

function Evidence({ data }) {
  return <>
    <span className="source-label">{SOURCES[data.source]}</span>
    <ul className="explanation-reasons">{data.reasons.map((reason,i) => <li key={i}>{reason}</li>)}</ul>
    {data.cf_support && <section className="evidence-section"><h3>Connected through training history</h3><p>Supporting products from positive training ratings. These are examples of the contributing seeds, not a complete history.</p>
      <ul className="support-products">{data.cf_support.seed_contributions.map(seed => <li key={seed.product.product_id}><Link to={`/products/${encodeURIComponent(seed.product.product_id)}`}>{seed.product.title_available ? seed.product.title : 'Title unavailable'}</Link></li>)}</ul>
    </section>}
    {data.content_support && <section className="evidence-section"><h3>Shared content features</h3><p>Title and category terms shared with the frozen positive-training profile. The model uses text, not product images.</p>
      <ul className="feature-chips">{data.content_support.top_shared_features.map((feature,i) => <li key={i}><span>{feature.term}</span><small>{feature.field}</small></li>)}</ul>
    </section>}
    {data.fusion && <section className="evidence-section"><h3>Two rankings, brought together</h3><p>Weighted reciprocal rank fusion combines available personalized signals. A missing component has no rank for this item.</p>
      <div className="fusion-ranks"><div><span>Collaborative rank</span><strong>{data.fusion.cf_rank === null ? 'Not present' : `#${data.fusion.cf_rank}`}</strong></div><div><span>Content rank</span><strong>{data.fusion.content_rank === null ? 'Not present' : `#${data.fusion.content_rank}`}</strong></div></div>
    </section>}
    {data.count_evidence && <section className="evidence-section"><h3>{data.source === 'popularity_fallback' ? 'A popularity starting point' : 'Observed in training'}</h3><p><strong>{data.count_evidence.training_interaction_count.toLocaleString()}</strong> rating interactions in the frozen training data. This is an interaction count, not a current marketplace rating.</p></section>}
    <details className="technical-details"><summary>Technical details</summary><p>Ranking scores order results. They are not probabilities or confidence percentages, and scores from different models are not directly comparable.</p>
      <dl><dt>Served model</dt><dd>{MODELS[data.model]}</dd><dt>Source</dt><dd>{data.source}</dd><dt>Ranking score</dt><dd>{data.ranking_score}</dd><dt>Score type</dt><dd>{data.score_type}</dd>
        {data.cf_support && <><dt>Total seed similarity</dt><dd>{data.cf_support.total_seed_similarity}</dd>{data.cf_support.seed_contributions.map(seed => <div className="technical-pair" key={seed.product.product_id}><dt>Seed similarity: {seed.product.title_available ? seed.product.title : 'Title unavailable'}</dt><dd>{seed.similarity}</dd></div>)}</>}
        {data.content_support && <><dt>Total feature contribution</dt><dd>{data.content_support.total_feature_contribution}</dd>{data.content_support.top_shared_features.map((feature,i) => <div className="technical-pair" key={i}><dt>{feature.field} feature: {feature.term}</dt><dd>{feature.dot_product_contribution}</dd></div>)}</>}
        {data.fusion && <><dt>Rank constant</dt><dd>{data.fusion.rank_constant}</dd><dt>Configured CF / content weights</dt><dd>{data.fusion.configured_cf_weight} / {1-data.fusion.configured_cf_weight}</dd><dt>Effective CF / content weights</dt><dd>{data.fusion.effective_cf_weight} / {data.fusion.effective_content_weight}</dd><dt>CF rank contribution</dt><dd>{data.fusion.cf_rank_contribution}</dd><dt>Content rank contribution</dt><dd>{data.fusion.content_rank_contribution}</dd></>}
      </dl><p>Displayed seeds and features are a limited selection; their totals include all contributors.</p>
    </details>
  </>;
}

export function ExplanationDialog({ product, resource, refreshing, missing, onClose, onRefresh }) {
  const ref = useRef(null), closeRef = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    const origin = previous?.closest?.('.recommendation-results');
    const dialog = ref.current;
    dialog.showModal(); closeRef.current.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      dialog.close(); document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
      else if (origin?.isConnected) {
        const replacement = [...origin.querySelectorAll('.recommendation-evidence')].find(el => el.dataset.productId === product.product_id)?.querySelector('.why-button');
        (replacement || origin.querySelector('#picks-heading'))?.focus({ preventScroll: true });
      }
    };
  }, [product.product_id]);
  function keyboard(event) {
    if (event.key === 'Escape') { event.preventDefault(); onClose(); }
    if (event.key !== 'Tab') return;
    const elements = [...ref.current.querySelectorAll('button:not(:disabled),a[href],summary,[tabindex="0"]')].filter(el => !el.closest('details:not([open])') || el.tagName === 'SUMMARY');
    const first = elements[0], last = elements.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
  const expired = ['BATCH_NOT_FOUND','RECOMMENDATION_NOT_FOUND'].includes(resource.error?.code);
  return <dialog ref={ref} className="explanation-dialog" aria-labelledby="explanation-heading" aria-describedby="explanation-product" onKeyDown={keyboard} onCancel={event => { event.preventDefault(); onClose(); }}>
    <header className="dialog-header"><div><span className="section-kicker">BEHIND THE CONNECTION</span><h2 id="explanation-heading">Why this recommendation?</h2></div><button ref={closeRef} type="button" className="dialog-close" aria-label="Close explanation" onClick={onClose}><X size={21} aria-hidden="true" /></button></header>
    <div className="dialog-body"><p id="explanation-product" className="explanation-product">{product.title_available ? product.title : 'Title unavailable'}</p>
      {(refreshing || resource.status === 'loading') && <div role="status" className="evidence-loading"><span className="loading-line" /><span className="loading-line" /><p>{refreshing ? 'Refreshing recommendations and checking this product…' : 'Loading verified recommendation evidence…'}</p></div>}
      {missing && <div role="status" className="explanation-notice"><h3>This product is no longer in the refreshed recommendations.</h3><p>No explanation was requested for it. Close this dialog to explore the new picks.</p></div>}
      {!refreshing && !missing && resource.status === 'error' && <div role="alert" className="explanation-notice"><h3>{expired ? 'Time for a fresh connection.' : 'The explanation couldn’t load.'}</h3><p>{resource.error.message}</p>{expired ? <><p>Refresh the recommendations to get a new batch. We’ll request evidence only if this product is still included.</p><Button onClick={onRefresh}>Refresh recommendations</Button></> : <Button variant="secondary" onClick={resource.retry}>Try explanation again</Button>}</div>}
      {!refreshing && !missing && resource.status === 'ready' && <Evidence data={resource.data} />}
    </div>
    <footer className="dialog-footer">Evidence comes from the frozen training snapshot. It does not describe newly learned preferences.</footer>
  </dialog>;
}
