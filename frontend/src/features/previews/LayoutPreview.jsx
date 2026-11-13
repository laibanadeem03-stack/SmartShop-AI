import { ArrowLeft, ArrowRight } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '../../components/ui/Button.jsx';

export function LayoutPreview({ kicker, title, description, children }) {
  return <div className="page-width preview-page">
    <Link to="/discover" className="back-link"><ArrowLeft size={16} aria-hidden="true" /> Back to Discover</Link>
    <div className="preview-page-heading"><span className="section-kicker">{kicker}</span><span className="layout-badge">Stage 1 · Layout preview</span><h1>{title}</h1><p>{description}</p></div>
    {children}
    <div className="preview-return"><p>This page is an initial layout. Its full experience will be connected in a later stage.</p><Button to="/discover" variant="secondary">Explore the catalog <ArrowRight size={16} aria-hidden="true" /></Button></div>
  </div>;
}
