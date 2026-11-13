import { useCallback, useEffect, useState } from 'react';
import { ApiError } from './catalog.js';

/** Keyed state prevents stale data flashing even before effect cleanup runs. */
export function useApiResource(key, load, enabled = true) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ key: null, status: 'idle', data: null, error: null });
  const retry = useCallback(() => setAttempt(n => n + 1), []);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let active = true;
    setState({ key, status: 'loading', data: null, error: null });
    const timeout = setTimeout(() => {
      if (!active) return;
      active = false; controller.abort();
      setState({ key, status: 'error', data: null, error: new ApiError('TIMEOUT', 'The local service took too long to respond. Please try again.') });
    }, 10000);
    load(controller.signal).then(data => {
      if (active && !controller.signal.aborted) setState({ key, status: 'ready', data, error: null });
    }).catch(error => {
      if (active && !controller.signal.aborted) setState({ key, status: 'error', data: null,
        error: error instanceof ApiError ? error : new ApiError('UNAVAILABLE', 'The local service could not be loaded. Please try again.') });
    }).finally(() => clearTimeout(timeout));
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [key, load, enabled, attempt]);
  const current = !enabled ? { status: 'idle', data: null, error: null } :
    state.key === key ? state : { status: 'loading', data: null, error: null };
  return { ...current, retry };
}
