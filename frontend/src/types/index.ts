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
}

export interface CommunicationChannelResult {
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
  communications?: {
    voice?: CommunicationChannelResult;
    message?: CommunicationChannelResult;
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

