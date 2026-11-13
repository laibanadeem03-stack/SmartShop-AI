import { useCallback } from 'react';
import { ArrowRight, ArrowUpRight, Cable, Check, Compass, Layers2, ListFilter, ScanLine, Search, ShieldCheck, Smartphone, Sparkles, Watch, X } from 'lucide-react';
import { Button } from '../../components/ui/Button.jsx';
import { ProductCard } from '../../components/products/ProductCard.jsx';
import { CatalogError, EmptyCatalog, ProductSkeletons } from '../../components/ui/CatalogStates.jsx';
import { Pagination } from '../../components/ui/Pagination.jsx';
import { useApiReadiness } from '../../api/ApiReadinessProvider.jsx';
import { useApiResource } from '../../api/useApiResource.js';
import { loadProducts, PAGE_SIZE } from '../../api/catalog.js';
import { FEATURED_CATEGORIES } from './catalogFilters.js';
import { useCatalogFilters } from './useCatalogFilters.js';

function DiscoveryArtwork() {
  return <div className="discovery-artwork" aria-hidden="true">
    <div className="artwork-orbit orbit-one" /><div className="artwork-orbit orbit-two" /><div className="artwork-orbit orbit-three" />
    <span className="artwork-dot dot-one" /><span className="artwork-dot dot-two" /><span className="artwork-dot dot-three" />
    <div className="artwork-hub"><Layers2 size={43} strokeWidth={1.4} /></div>
    <div className="floating-node node-phone"><Smartphone size={32} strokeWidth={1.3} /><span>Everyday essentials</span><ArrowUpRight size={13} /></div>
    <div className="floating-node node-cable"><Cable size={28} strokeWidth={1.3} /><span>Better connections</span></div>
    <div className="floating-node node-watch"><Watch size={30} strokeWidth={1.3} /><span>Little discoveries</span></div>
    <div className="artwork-caption"><span className="tiny-dot" /> A WORLD OF CONNECTIONS</div>
    <span className="artwork-coordinate">EXPLORE / CONNECT / DISCOVER</span>
  </div>;
}

export function DiscoverPage() {
  const readiness = useApiReadiness();
  const filters = useCatalogFilters();
  const { q, category, page, draft, isDebouncing } = filters;
  const load = useCallback(signal => loadProducts({ q, category, page }, signal), [q, category, page]);
  const result = useApiResource(JSON.stringify(['catalog', q, category, page]), load, readiness.status === 'ready' && !isDebouncing);
  const data = result.data;
  const products = data?.items || [];
  const total = data?.total ?? 0;
  const pages = Math.ceil(total / PAGE_SIZE);
  const loading = readiness.status === 'loading' || isDebouncing || result.status === 'loading' || result.status === 'idle';
  const error = readiness.error || result.error;
  const retry = readiness.status === 'error' ? readiness.retry : result.retry;
  const outOfRange = result.status === 'ready' && total > 0 && products.length === 0;
  function changePage(next) {
    filters.setPage(next);
    requestAnimationFrame(() => {
      const section = document.getElementById('collection');
      section?.scrollIntoView?.({ block: 'start' });
      document.getElementById('collection-heading')?.focus({ preventScroll: true });
    });
  }
  return <div className="discover-page page-width">
    <section className="hero" aria-labelledby="discover-heading">
      <div className="hero-copy">
        <span className="hero-kicker"><span className="tiny-dot" /> TECH, THOUGHTFULLY DISCOVERED</span>
        <h1 id="discover-heading">Good tech.<br /><span>Great connections.</span></h1>
        <p className="hero-description">A little less searching. A little more discovery.<br className="desktop-break" /> Explore phones and accessories with a fresh perspective.</p>
        <div className="hero-actions"><Button href="#collection">Explore the collection <ArrowRight size={17} aria-hidden="true" /></Button>
          <Button to="/insights" variant="quiet">Behind the discovery <ArrowUpRight size={16} aria-hidden="true" /></Button></div>
        <div className="hero-footnote"><ShieldCheck size={15} aria-hidden="true" /> Verified titles & categories <span /> Phones & accessories</div>
      </div>
      <DiscoveryArtwork />
    </section>

    <section className="discovery-values" aria-label="Our discovery approach">
      <div className="value-item"><span className="value-icon"><ScanLine size={20} strokeWidth={1.6} aria-hidden="true" /></span><div><h2>Real information.</h2><p>Product titles and categories, as provided.</p></div></div>
      <div className="value-item"><span className="value-icon"><Compass size={20} strokeWidth={1.6} aria-hidden="true" /></span><div><h2>A considered collection.</h2><p>Phones, accessories, and possibilities.</p></div></div>
      <div className="value-item"><span className="value-icon"><Sparkles size={20} strokeWidth={1.6} aria-hidden="true" /></span><div><h2>More context, less guesswork.</h2><p>Discovery with explanation at its heart.</p></div></div>
    </section>

    <section className="collection" id="collection" data-page={page} data-query={q} data-category={category} aria-labelledby="collection-heading" aria-busy={!error && loading}>
      <div className="collection-heading"><div><div className="section-kicker">THE DISCOVERY EDIT</div><h2 id="collection-heading" tabIndex={-1}>Something worth exploring.</h2></div>
        <div className="preview-badge"><span className="tiny-dot" /> Verified product catalog</div></div>
      <div className="collection-toolbar">
        <div className="search-field"><Search size={19} aria-hidden="true" /><label htmlFor="catalog-search" className="sr-only">Search the product catalog</label>
          <input id="catalog-search" type="search" placeholder="Search phones, accessories, model numbers…" value={draft} maxLength={200} onChange={e => filters.setDraft(e.target.value)} aria-describedby="catalog-search-help" />
          {draft && <button type="button" className="icon-button" onClick={() => filters.setDraft('')} aria-label="Clear search"><X size={16} aria-hidden="true" /></button>}
          <span className="search-shortcut" aria-hidden="true">CATALOG SEARCH</span>
        </div>
        <div className="loaded-count" role="status" aria-live="polite">
          {error ? 'Catalog unavailable' : loading ? (isDebouncing ? 'Updating search…' : 'Loading products…') : outOfRange ? `${total.toLocaleString('en-US')} products available` : total === 0 ? 'No products found' :
            <><strong>{((page - 1) * PAGE_SIZE + 1).toLocaleString('en-US')}–{((page - 1) * PAGE_SIZE + products.length).toLocaleString('en-US')}</strong> <span>of {total.toLocaleString('en-US')} products</span></>}
        </div>
      </div>
      <div className="category-filters" aria-label="Featured category filters"><span className="filter-label"><ListFilter size={15} aria-hidden="true" /> Featured categories</span>
        {['', ...FEATURED_CATEGORIES].map(label => <button type="button" key={label || 'all'} className={`category-chip ${category === label ? 'selected' : ''}`} aria-pressed={category === label} onClick={() => filters.setCategory(label)}>
          {category === label && <Check size={13} aria-hidden="true" />}{label || 'All items'}
        </button>)}
      </div>
      <p className="preview-scope" id="catalog-search-help">Search all product titles and categories. Featured filters match whole category labels; they are not an exhaustive category list.</p>
      {filters.notice && <p className="catalog-notice" role="status">{filters.notice}</p>}
      {(q || category) && <div className="active-filters"><span>Filtered collection</span><Button variant="quiet" onClick={filters.clear}>Clear all filters <X size={14} aria-hidden="true" /></Button></div>}
      {error ? <CatalogError error={error} retry={retry} /> : loading ? <ProductSkeletons label={isDebouncing ? 'Updating search results' : 'Loading products'} /> : outOfRange ?
        <EmptyCatalog title="This page is outside the collection." action={() => changePage(1)} actionLabel="Go to first page">There are {pages.toLocaleString('en-US')} pages for these filters. Return to page one to continue browsing.</EmptyCatalog> : total === 0 ?
        <EmptyCatalog title="No products found." action={filters.clear}>Try a broader search or clear the category filter. No replacement products have been added.</EmptyCatalog> :
        <div className="product-grid">{products.map((product, i) => <ProductCard key={product.product_id} product={product} index={(page - 1) * PAGE_SIZE + i} />)}</div>}
      {!error && !loading && <Pagination page={page} pages={pages} disabled={isDebouncing} onChange={changePage} />}
    </section>
    <aside className="next-discovery"><div className="next-icon"><Sparkles size={25} strokeWidth={1.5} aria-hidden="true" /></div><div><span className="section-kicker">A MORE PERSONAL PERSPECTIVE</span><h2>A collection that connects with you.</h2><p>Explore personalized picks with an anonymous demo profile and evidence behind every recommendation.</p></div><Button to="/for-you" variant="secondary">Explore For You <ArrowUpRight size={16} aria-hidden="true" /></Button></aside>
  </div>;
}
