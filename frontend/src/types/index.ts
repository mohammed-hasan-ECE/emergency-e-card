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
  emergency_contact_phone?: string;
  location_publish_token?: string | null;
}

export interface CommunicationChannelResult {
  channel: string;
  provider: string;
  status: string;
  external_id?: string | null;
  error?: string | null;
}

export interface NotificationChannelResult {
  channel: string;
  provider: string;
  status: string;
  external_id?: string | null;
  error?: string | null;
}

export interface SOSResponse {
  message: string;
  alert_id: string;
  profile_id: string;
  full_name: string;
  blood_group: string;
  allergies: string;
  medical_conditions: string;
  medications: string;
  emergency_contacts: string;
  emergency_contact_phone: string | null;
  nearby_users: NearbyUser[];
  acknowledged_responders?: AcknowledgedResponder[];
  tracking_url?: string;
  communications?: {
    voice?: CommunicationChannelResult;
    message?: CommunicationChannelResult;
  };
  notifications?: {
    whatsapp?: NotificationChannelResult;
    sms?: NotificationChannelResult;
  };
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
  expires_at?: string;
  has_acknowledged?: boolean;
}

export interface AcknowledgedResponder {
  profile_id: string;
  full_name: string;
  responder_phone?: string;
  status: string;
}

export interface TrackInfo {
  person_name: string;
  tracking_active: boolean;
  location_status: string;
  location_updated_at: string | null;
  has_location: boolean;
  maps_url: string | null;
  map_embed_url: string | null;
}

