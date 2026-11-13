import { createContext, useContext } from 'react';
import { loadReadiness } from './catalog.js';
import { useApiResource } from './useApiResource.js';

const ReadinessContext = createContext(null);
export function ApiReadinessProvider({ children }) {
  const readiness = useApiResource('readiness', loadReadiness);
  return <ReadinessContext.Provider value={readiness}>{children}</ReadinessContext.Provider>;
}
export function useApiReadiness() {
  const value = useContext(ReadinessContext);
  if (!value) throw new Error('Readiness context is required');
  return value;
}
