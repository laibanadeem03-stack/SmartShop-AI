import { useEffect, useRef } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router';
import { ArrowUpRight, ChartNoAxesCombined, Compass, Sparkles, ArrowRight } from 'lucide-react';
import { Brand } from './Brand.jsx';
import { useApiReadiness } from '../../api/ApiReadinessProvider.jsx';

const links = [{ to: '/discover', label: 'Discover', icon: Compass },
  { to: '/for-you', label: 'For You', icon: Sparkles },
  { to: '/insights', label: 'AI Insights', icon: ChartNoAxesCombined }];

function Navigation({ mobile = false }) {
  return <nav aria-label={mobile ? 'Mobile navigation' : 'Main navigation'} className={mobile ? 'mobile-nav' : 'desktop-nav'}>
    {links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
      <Icon size={17} strokeWidth={1.8} aria-hidden="true" /><span>{label}</span>
    </NavLink>)}
  </nav>;
}

export function AppShell() {
  const preview = useApiReadiness();
  const location = useLocation();
  const main = useRef(null);
  const previousPath = useRef(location.pathname);
  useEffect(() => {
    const name = location.pathname.startsWith('/for-you') ? 'For You' : location.pathname.startsWith('/insights') ? 'AI Insights' :
      location.pathname.startsWith('/products') ? 'Product details' : 'Discover';
    document.title = `${name} · SmartShop AI`;
    if (!location.hash) window.scrollTo?.(0, 0);
    if (previousPath.current !== location.pathname && !location.hash) main.current?.focus({ preventScroll: true });
    previousPath.current = location.pathname;
  }, [location.pathname, location.hash]);
  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="site-header"><div className="page-width header-inner">
      <Brand /><Navigation />
      <div className="header-actions">
        <span className={`connection connection-${preview.status}`}>
          <span className="status-dot" aria-hidden="true" />
          {preview.status === 'ready' ? 'Catalog connected' : preview.status === 'loading' ? 'Connecting catalog' : 'Catalog offline'}
        </span>
        <span className="edition-label">Discovery edition <ArrowUpRight size={14} aria-hidden="true" /></span>
      </div>
    </div></header>
    <main ref={main} id="main-content" tabIndex={-1}><Outlet /></main>
    <footer className="site-footer page-width">
      <div><Brand /><p>A little more clarity.<br />A better way to explore.</p></div>
      <div className="footer-note"><span className="eyebrow">THOUGHTFULLY CONNECTED</span><p>Historical product metadata from Amazon Reviews 2023,<br className="desktop-break" /> McAuley Lab, UC San Diego. No current prices or availability.</p></div>
      <NavLink to="/insights" className="text-link">Behind the discovery <ArrowRight size={15} aria-hidden="true" /></NavLink>
    </footer>
    <Navigation mobile />
  </>;
}
