import { useEffect, useMemo, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router';
import { filterParams, parseFilters } from './catalogFilters.js';

export function useCatalogFilters() {
  const location = useLocation();
  const [, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(location.search), [location.search]);
  const [draft, setDraft] = useState(filters.q);
  const [notice, setNotice] = useState('');
  const canonical = filterParams(filters).toString();
  useEffect(() => {
    if (filters.unknownCategory) setNotice('An unrecognized featured-category filter was cleared. Choose one of the verified filters below.');
    if (location.search.slice(1) !== canonical) setSearchParams(canonical, { replace: true });
  }, [canonical, filters.unknownCategory, location.search, setSearchParams]);
  useEffect(() => { setDraft(filters.q); }, [location.search, filters.q]);
  useEffect(() => {
    if (draft.trim() === filters.q) return;
    const timer = setTimeout(() => setSearchParams(filterParams({ ...filters, q: draft.trim(), page: 1 }), { replace: true }), 300);
    return () => clearTimeout(timer);
  }, [draft, filters, setSearchParams]);
  const update = next => { setNotice(''); setSearchParams(filterParams({ ...filters, q: draft.trim(), ...next })); };
  return { ...filters, draft, setDraft, notice, isDebouncing: draft.trim() !== filters.q,
    setCategory: category => update({ category, page: 1 }), setPage: page => update({ page }),
    clear: () => { setDraft(''); update({ q: '', category: '', page: 1 }); } };
}
