const PROFILE_ID_KEY = 'emergency_ecard_profile_id';
const LOCATION_PUBLISH_TOKEN_KEY = 'emergency_ecard_location_token';

export const storageService = {
  getProfileId: (): string | null => {
    return localStorage.getItem(PROFILE_ID_KEY);
  },
  
  setProfileId: (id: string): void => {
    localStorage.setItem(PROFILE_ID_KEY, id);
  },
  
  clearProfileId: (): void => {
    localStorage.removeItem(PROFILE_ID_KEY);
  },

  getLocationPublishToken: (): string | null => {
    return localStorage.getItem(LOCATION_PUBLISH_TOKEN_KEY);
  },

  setLocationPublishToken: (token: string): void => {
    localStorage.setItem(LOCATION_PUBLISH_TOKEN_KEY, token);
  },

  clearLocationPublishToken: (): void => {
    localStorage.removeItem(LOCATION_PUBLISH_TOKEN_KEY);
  }
};
