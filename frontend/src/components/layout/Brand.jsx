import { Layers2 } from 'lucide-react';
import { Link } from 'react-router';

export function Brand() {
  return <Link to="/discover" className="brand" aria-label="SmartShop AI home">
    <span className="brand-mark"><Layers2 size={22} strokeWidth={1.8} aria-hidden="true" /></span>
    <span>SmartShop<span className="brand-ai">AI</span></span>
  </Link>;
}
