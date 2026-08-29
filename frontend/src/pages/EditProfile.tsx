import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Profile } from '../types';
import { profileService } from '../services/api';
import { storageService } from '../services/storage';
import { User, Phone, Droplet, AlertCircle, Activity, Pill, Users, Loader2, ArrowLeft } from 'lucide-react';

export function EditProfile() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState<Omit<Profile, 'id'>>({
    full_name: '',
    phone_number: '',
    blood_group: '',
    allergies: '',
    medical_conditions: '',
    medications: '',
    emergency_contacts: '',
  });

  useEffect(() => {
    const fetchProfile = async () => {
      const profileId = storageService.getProfileId();
      
      if (!profileId) {
        navigate('/create');
        return;
      }

      try {
        const data = await profileService.getProfile(profileId);
        setFormData({
          full_name: data.full_name || '',
          phone_number: data.phone_number || '',
          blood_group: data.blood_group || '',
          allergies: data.allergies || '',
          medical_conditions: data.medical_conditions || '',
          medications: data.medications || '',
          emergency_contacts: data.emergency_contacts || '',
        });
      } catch (err: any) {
        console.error('Error fetching profile:', err);
        setError('Could not load profile data for editing.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, [navigate]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const profileId = storageService.getProfileId();
    
    if (!profileId) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await profileService.updateProfile(profileId, formData);
      navigate('/card');
    } catch (err: any) {
      console.error('Error updating profile:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to update profile.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <Loader2 className="w-10 h-10 text-brand-500 animate-spin" />
        <p className="text-gray-500 font-medium">Loading profile data...</p>
      </div>
    );
  }

  return (
    <div className="py-4 space-y-6">
      <div className="flex items-center gap-3">
        <button 
          onClick={() => navigate('/card')}
          className="p-2 bg-gray-100 hover:bg-gray-200 rounded-full transition-colors text-gray-600"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Edit Profile</h1>
          <p className="text-gray-500 text-sm mt-0.5">Update your medical information.</p>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-md flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5 bg-white p-5 rounded-2xl shadow-sm border border-gray-100">
        <div className="space-y-1.5">
          <label htmlFor="full_name" className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <User className="w-4 h-4 text-gray-400" />
            Full Name *
          </label>
          <input
            type="text"
            id="full_name"
            name="full_name"
            required
            value={formData.full_name}
            onChange={handleChange}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="phone_number" className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <Phone className="w-4 h-4 text-gray-400" />
            Phone Number *
          </label>
          <input
            type="tel"
            id="phone_number"
            name="phone_number"
            required
            value={formData.phone_number}
            onChange={handleChange}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="blood_group" className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <Droplet className="w-4 h-4 text-brand-500" />
            Blood Group
          </label>
          <select
            id="blood_group"
            name="blood_group"
            value={formData.blood_group}
            onChange={handleChange}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all bg-white"
          >
            <option value="">Select Blood Group</option>
            <option value="A+">A+</option>
            <option value="A-">A-</option>
            <option value="B+">B+</option>
            <option value="B-">B-</option>
            <option value="AB+">AB+</option>
            <option value="AB-">AB-</option>
            <option value="O+">O+</option>
            <option value="O-">O-</option>
            <option value="Unknown">Unknown</option>
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="allergies" className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-orange-500" />
            Allergies
          </label>
          <textarea
            id="allergies"
            name="allergies"
            rows={2}
            value={formData.allergies}
            onChange={handleChange}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all resize-none"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="medical_conditions" className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <Activity className="w-4 h-4 text-blue-500" />
            Medical Conditions
          </label>
          <textarea
            id="medical_conditions"
            name="medical_conditions"
            rows={2}
            value={formData.medical_conditions}
            onChange={handleChange}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all resize-none"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="medications" className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <Pill className="w-4 h-4 text-purple-500" />
            Current Medications
          </label>
          <textarea
            id="medications"
            name="medications"
            rows={2}
            value={formData.medications}
            onChange={handleChange}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all resize-none"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="emergency_contacts" className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <Users className="w-4 h-4 text-green-500" />
            Emergency Contacts
          </label>
          <textarea
            id="emergency_contacts"
            name="emergency_contacts"
            rows={3}
            value={formData.emergency_contacts}
            onChange={handleChange}
            className="w-full px-4 py-2.5 rounded-xl border border-gray-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all resize-none"
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full bg-brand-600 hover:bg-brand-700 text-white font-bold py-3.5 px-4 rounded-xl transition-colors shadow-sm flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed mt-4"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Saving Changes...
            </>
          ) : (
            'Save Changes'
          )}
        </button>
      </form>
    </div>
  );
}
