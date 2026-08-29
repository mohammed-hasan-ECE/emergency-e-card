export interface Profile {
  id?: string;
  full_name: string;
  phone_number: string;
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
}
