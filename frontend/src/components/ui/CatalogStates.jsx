import { Cable, Search } from 'lucide-react';
import { Button } from './Button.jsx';
export function ProductSkeletons({ label = 'Loading products', count = 8 }) {
  return <div className="product-grid" role="status" aria-label={label}>
    {Array.from({ length: count }, (_, i) => <div key={i} className="product-skeleton" aria-hidden="true"><div /><span /><span /><span /></div>)}
    <span className="sr-only">{label}</span>
  </div>;
}
export function CatalogError({ error, retry, title = 'A little connection trouble.', headingLevel = 2 }) {
  const Heading = headingLevel === 1 ? 'h1' : 'h2';
  return <div className="empty-state" role="alert"><span className="empty-icon"><Cable size={28} aria-hidden="true" /></span><Heading>{title}</Heading><p>{error?.message || 'The catalog service is unavailable. Please try again.'}</p><Button onClick={retry} variant="secondary">Try again</Button></div>;
}
export function EmptyCatalog({ title, children, action, actionLabel = 'Clear filters' }) {
  return <div className="empty-state"><span className="empty-icon"><Search size={28} aria-hidden="true" /></span><h2>{title}</h2><p>{children}</p>{action && <Button variant="secondary" onClick={action}>{actionLabel}</Button>}</div>;
}
