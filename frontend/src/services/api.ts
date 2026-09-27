import axios from 'axios';
import type { Profile, SOSResponse, NearbyAlert } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL;
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

  updateProfileLocation: async (
    id: string,
    latitude: number,
    longitude: number
  ): Promise<Profile> => {
    const response = await api.put<Profile>(`/profiles/${id}`, {
      latitude: latitude.toString(),
      longitude: longitude.toString(),
    });
    return response.data;
  },
};

export const sosService = {
  triggerSOS: async (
  id: string,
  latitude: number,
  longitude: number
): Promise<SOSResponse> => {
  const response = await api.post<SOSResponse>(
    `/sos/${id}?latitude=${latitude}&longitude=${longitude}`
  );
  return response.data;
},

  getNearbyUsers: async (id: string) => {
    const response = await api.get(`/nearby/${id}`);
    return response.data;
  },

  getNearbyAlerts: async (id: string): Promise<{
    responder_profile_id: string;
    radius_km: number;
    nearby_alerts: NearbyAlert[];
  }> => {
    const response = await api.get(`/alerts/${id}`);
    return response.data;
  },

  acknowledgeAlert: async (alertId: string, responderId: string) => {
    const response = await api.post(`/alerts/${alertId}/respond?profile_id=${responderId}`);
    return response.data;
  },

  resolveAlert: async (alertId: string, profileId: string) => {
    const response = await api.post(`/alerts/${alertId}/resolve?profile_id=${profileId}`);
    return response.data;
  },
};