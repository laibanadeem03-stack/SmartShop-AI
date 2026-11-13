import { useCallback } from 'react';
import { Link, useLocation, useParams } from 'react-router';
import { ArrowLeft, Layers2, ShieldCheck } from 'lucide-react';
import { useApiReadiness } from '../../api/ApiReadinessProvider.jsx';
import { useApiResource } from '../../api/useApiResource.js';
import { loadProduct, loadSimilarProducts } from '../../api/catalog.js';
import { categoryAppearance, categoryLabel, ProductCard } from '../../components/products/ProductCard.jsx';
import { CatalogError, ProductSkeletons } from '../../components/ui/CatalogStates.jsx';
import { Button } from '../../components/ui/Button.jsx';

function SimilarProducts({ product }) {
  const load = useCallback(signal => loadSimilarProducts(product.product_id, signal), [product.product_id]);
  const resource = useApiResource('similar:'+product.product_id, load, product.recommendation_eligible);
  return <section className="similar-products" aria-labelledby="similar-heading">
    <div className="collection-heading"><div><span className="section-kicker">KEEP EXPLORING</span><h2 id="similar-heading">Related discoveries</h2></div><span className="preview-badge">Content similarity</span></div>
    {!product.recommendation_eligible || resource.error?.status === 409 ?
      <div className="similar-message"><Layers2 size={25} aria-hidden="true" /><div><h3>Available for browsing.</h3><p>This product is outside the frozen recommendation catalog, so similar-product recommendations are unavailable.</p></div></div> :
      resource.status === 'loading' || resource.status === 'idle' ? <ProductSkeletons count={4} label="Loading similar products" /> : resource.error ?
        <CatalogError title="Related discoveries couldn’t load." error={resource.error} retry={resource.retry} /> : resource.data.items.length === 0 ?
          <div className="similar-message"><Layers2 size={25} aria-hidden="true" /><div><h3>No similar products found.</h3><p>The content model has no positive text matches to show for this item. Popular products have not been substituted.</p></div></div> :
          <><p className="similar-description">{resource.data.items.length} related products, ordered by shared title and category features.</p><div className="product-grid similar-grid">{resource.data.items.map((item, i) => <ProductCard key={item.product.product_id} product={item.product} index={i} />)}</div></>}
  </section>;
}

export function ProductDetailsPage() {
  const { productId } = useParams();
  const location = useLocation();
  const readiness = useApiReadiness();
  const validId = /^[A-Za-z0-9_-]{1,64}$/.test(productId || '');
  const load = useCallback(signal => loadProduct(productId, signal), [productId]);
  const resource = useApiResource('detail:'+productId, load, readiness.status === 'ready' && validId);
  const product = resource.data;
  const error = readiness.error || resource.error;
  const retry = readiness.status === 'error' ? readiness.retry : resource.retry;
  const catalogSearch = typeof location.state?.catalogSearch === 'string' && location.state.catalogSearch.startsWith('?') ? location.state.catalogSearch : '';
  const back = '/discover'+catalogSearch;
  let content;
  if (!validId || resource.error?.status === 404) {
    content = <div className="empty-state"><h1>Product not found.</h1><p>This product could not be found in the catalog. Return to the collection to continue exploring.</p><Button to={back} variant="secondary">Back to results</Button></div>;
  } else if (error) {
    content = <CatalogError error={error} retry={retry} title="This product couldn’t load." headingLevel={1} />;
  } else if (!product) {
    content = <section role="status" aria-label="Loading product details" className="detail-skeleton"><div /><div><h1>Loading product details…</h1><span /><span /><span /></div></section>;
  } else {
    const { Icon, tone } = categoryAppearance(product);
    content = <>
      <section className="product-preview-layout">
        <div className={`detail-category-art art-${tone}`}><span className="detail-orbit" aria-hidden="true" /><Icon size={110} strokeWidth={0.9} aria-hidden="true" /><span>CATEGORY ILLUSTRATION · NOT A PRODUCT PHOTO</span></div>
        <div className="detail-copy"><p className="product-category">{categoryLabel(product)}</p><h1>{product.title_available ? product.title : 'Title unavailable'}</h1>
          <span className={`detail-eligibility ${product.recommendation_eligible ? '' : 'browse-only'}`}>{product.recommendation_eligible ? <ShieldCheck size={16} aria-hidden="true" /> : <Layers2 size={16} aria-hidden="true" />}{product.recommendation_eligible ? 'In the recommendation catalog' : 'Available for browsing'}</span>
          <dl><div><dt>Product ID</dt><dd>{product.product_id}</dd></div><div><dt>Main category</dt><dd>{product.main_category?.trim() ? product.main_category : 'Not provided'}</dd></div><div><dt>Category hierarchy</dt><dd>{product.categories.some(c => c.trim()) ? product.categories.filter(c => c.trim()).join(' / ') : 'No category hierarchy provided'}</dd></div></dl>
          <div className="training-statistics" aria-label="Historical training statistics">
            <div><span>Training rating interactions</span><strong>{product.training_interaction_count === null ? 'Not available' : product.training_interaction_count.toLocaleString('en-US')}</strong></div>
            <div><span>Training-set mean rating</span><strong>{product.training_mean_rating === null ? 'Not available' : `${product.training_mean_rating.toFixed(2)} / 5`}</strong></div>
          </div>
          <p className="detail-source-note">Historical training data only, not current marketplace reviews. “Not available” indicates missing training statistics. Current price, stock and specifications are not provided.</p>
        </div>
      </section>
      <SimilarProducts key={product.product_id} product={product} />
    </>;
  }
  return <div className="page-width preview-page product-details-page" data-product-id={product?.product_id}><Link to={back} className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Back to results</Link><div className="detail-page-kicker"><span className="section-kicker">A CLOSER LOOK</span></div>{content}</div>;
}
