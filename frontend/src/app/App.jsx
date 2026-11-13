import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router';
import { ApiReadinessProvider } from '../api/ApiReadinessProvider.jsx';
import { DiscoverPage } from '../features/catalog/DiscoverPage.jsx';
import { ForYouPage } from '../features/recommendations/ForYouPage.jsx';
import { ProfileProvider } from '../features/recommendations/ProfileProvider.jsx';
import { ProductDetailsPage } from '../features/catalog/ProductDetailsPage.jsx';
import { Button } from '../components/ui/Button.jsx';
import { AppShell } from '../components/layout/AppShell.jsx';
const InsightsPage = lazy(() => import('../features/insights/InsightsPage.jsx').then(module => ({default:module.InsightsPage})));

export function App() {
  return <ApiReadinessProvider><ProfileProvider><div className="min-h-screen"><Routes>
    <Route element={<AppShell />}>
      <Route index element={<Navigate to="/discover" replace />} />
      <Route path="discover" element={<DiscoverPage />} />
      <Route path="for-you" element={<ForYouPage />} />
      <Route path="insights" element={<Suspense fallback={<div className="page-width preview-page" role="status">Loading AI Insights…</div>}><InsightsPage /></Suspense>} />
      <Route path="products/:productId" element={<ProductDetailsPage />} />
      <Route path="*" element={<div className="page-width preview-page"><div className="empty-state"><h1>Let’s find your way back.</h1><p>This page isn’t part of the collection. Return to Discover to explore the catalog.</p><Button to="/discover" variant="secondary">Explore the catalog</Button></div></div>} />
    </Route>
  </Routes></div></ProfileProvider></ApiReadinessProvider>;
}
