import { createContext, useContext, useState } from 'react';
import { validAlias } from '../../api/recommendations.js';

export const PROFILE_KEY = 'smartshop.selected-profile.v1';
const ProfileContext = createContext(null);
function storedProfile() {
  try {
    const value = JSON.parse(localStorage.getItem(PROFILE_KEY));
    return validAlias(value?.public_user_id) && ['dataset_backed','new_demo'].includes(value.profile_type) ? { public_user_id: value.public_user_id, profile_type: value.profile_type } : null;
  } catch { return null; }
}
export function ProfileProvider({ children }) {
  const [selected, setSelected] = useState(storedProfile);
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  function select(profile) {
    const value = profile ? { public_user_id: profile.public_user_id, profile_type: profile.profile_type } : null;
    setSelected(value);
    try { if (value) localStorage.setItem(PROFILE_KEY, JSON.stringify(value)); else localStorage.removeItem(PROFILE_KEY); setStorageUnavailable(false); }
    catch { setStorageUnavailable(true); }
  }
  return <ProfileContext.Provider value={{ selected, select, storageUnavailable }}>{children}</ProfileContext.Provider>;
}
export const useProfile = () => useContext(ProfileContext);
