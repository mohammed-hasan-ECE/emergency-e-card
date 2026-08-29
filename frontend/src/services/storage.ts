const PROFILE_ID_KEY = 'emergency_ecard_profile_id';

export const storageService = {
  getProfileId: (): string | null => {
    return localStorage.getItem(PROFILE_ID_KEY);
  },
  
  setProfileId: (id: string): void => {
    localStorage.setItem(PROFILE_ID_KEY, id);
  },
  
  clearProfileId: (): void => {
    localStorage.removeItem(PROFILE_ID_KEY);
  }
};
