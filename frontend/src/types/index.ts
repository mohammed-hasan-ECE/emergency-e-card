export interface Profile {
  id?: string;
  full_name: string;
  phone_number: string;
  latitude?: string;
  longitude?: string;
  blood_group: string;
  allergies: string;
  medical_conditions: string;
  medications: string;
  emergency_contacts: string;
}

export interface SOSResponse {
  message: string;
  profile_id: string;
  full_name: string;
  blood_group: string;
  allergies: string;
  medical_conditions: string;
  emergency_contacts: string;
  nearby_users: NearbyUser[];
}
export interface NearbyUser {
  profile_id: string;
  full_name: string;
  distance_km: number;
}
export interface NearbyAlert {
  alert_id: string;
  profile_id: string;
  full_name: string | null;
  latitude: string;
  longitude: string;
  distance_km: number;
}

