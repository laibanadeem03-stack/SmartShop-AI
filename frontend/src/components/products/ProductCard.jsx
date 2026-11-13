import { ArrowUpRight, Cable, Headphones, Layers2, Package, ShieldCheck, Smartphone, Watch, Zap } from 'lucide-react';
import { Link, useLocation } from 'react-router';

export function categoryLabel(product) {
  return [...product.categories].reverse().find(c => c.trim()) || (product.main_category?.trim() ? product.main_category : 'Category unavailable');
}

export function categoryAppearance(product) {
  const category = categoryLabel(product).toLowerCase();
  if (/watch|wearable/.test(category)) return { Icon: Watch, tone: 'teal' };
  if (/charger|power|batter/.test(category)) return { Icon: Zap, tone: 'amber' };
  if (/cable|cord|adapter/.test(category)) return { Icon: Cable, tone: 'blue' };
  if (/screen|case|holster|sleeve/.test(category)) return { Icon: Layers2, tone: 'indigo' };
  if (/headphone|headset|audio/.test(category)) return { Icon: Headphones, tone: 'rose' };
  if (/phone/.test(category)) return { Icon: Smartphone, tone: 'teal' };
  return { Icon: Package, tone: 'blue' };
}

export function ProductCard({ product, index = 0, children }) {
  const location = useLocation();
  const catalogSearch = location.pathname === '/discover' ? location.search : location.state?.catalogSearch || '';
  const navigationState = { catalogSearch };
  const { Icon, tone } = categoryAppearance(product);
  return <article className="product-card">
    <div className={`category-art art-${tone}`}>
      <span className="art-grid" aria-hidden="true" />
      <span className="art-ring" aria-hidden="true" />
      <span className="category-art-icon"><Icon size={46} strokeWidth={1.1} aria-hidden="true" /></span>
      <span className="art-caption">CATEGORY STUDY</span>
      <span className="art-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
    </div>
    <div className="product-card-body">
      <p className="product-category">{categoryLabel(product)}</p>
      <h3><Link state={navigationState} to={`/products/${encodeURIComponent(product.product_id)}`}>{product.title_available ? product.title : 'Title unavailable'}</Link></h3>
      <div className="product-card-bottom">
        <span className={`eligibility ${product.recommendation_eligible ? '' : 'browse-only'}`}>
          {product.recommendation_eligible && <ShieldCheck size={13} aria-hidden="true" />}
          {product.recommendation_eligible ? 'In recommendation catalog' : 'Browse-only item'}
        </span>
        <Link state={navigationState} to={`/products/${encodeURIComponent(product.product_id)}`} className="card-open" aria-label={`View product details: ${product.title}`}>
          <ArrowUpRight size={17} aria-hidden="true" />
        </Link>
      </div>
      {children}
    </div>
  </article>;
}
