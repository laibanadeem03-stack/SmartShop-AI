import { ArrowLeft, ArrowRight } from 'lucide-react';
import { Button } from './Button.jsx';
export function Pagination({ page, pages, disabled, onChange }) {
  if (pages < 1 || page > pages) return null;
  return <nav className="catalog-pagination" aria-label="Catalog pagination">
    <Button variant="secondary" disabled={disabled || page <= 1} onClick={() => onChange(page - 1)}><ArrowLeft size={16} aria-hidden="true" /> Previous</Button>
    <span className="page-indicator" aria-current="page">Page <strong>{page.toLocaleString('en-US')}</strong> of {pages.toLocaleString('en-US')}</span>
    <Button variant="secondary" disabled={disabled || page >= pages} onClick={() => onChange(page + 1)}>Next <ArrowRight size={16} aria-hidden="true" /></Button>
  </nav>;
}
