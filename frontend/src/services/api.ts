import axios from 'axios';
import type { Profile, SOSResponse } from '../types';

const API_BASE_URL = 'https://emergency-e-card.onrender.com';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const profileService = {
  createProfile: async (data: Omit<Profile, 'id'>): Promise<Profile> => {
    const response = await api.post<Profile>('/profiles/', data);
    return response.data;
  },

  getProfile: async (id: string): Promise<Profile> => {
    const response = await api.get<Profile>(`/profiles/${id}`);
    return response.data;
  },

  updateProfile: async (id: string, data: Omit<Profile, 'id'>): Promise<Profile> => {
    const response = await api.put<Profile>(`/profiles/${id}`, data);
    return response.data;
  },
};

export const sosService = {
  triggerSOS: async (id: string): Promise<SOSResponse> => {
    const response = await api.get<SOSResponse>(`/sos/${id}`);
    return response.data;
  },
};
