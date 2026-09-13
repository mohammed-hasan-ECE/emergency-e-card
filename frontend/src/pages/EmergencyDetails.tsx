import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import type { Profile } from '../types';
import { profileService } from '../services/api';
import { 
  Phone, Droplet, AlertCircle, Activity, 
  Pill, Users, Loader2, ArrowLeft 
} from 'lucide-react';

export function EmergencyDetails() {
  const { profileId } = useParams<{ profileId: string }>();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchProfile = async () => {
      if (!profileId) {
        setError('No profile ID provided.');
        setIsLoading(false);
        return;
      }

      try {
        const data = await profileService.getProfile(profileId);
        setProfile(data);
      } catch (err: any) {
        console.error('Error fetching emergency profile:', err);
        setError('Could not load emergency details. The profile may have been deleted or there is a network issue.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, [profileId]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <Loader2 className="w-10 h-10 text-red-500 animate-spin" />
        <p className="text-gray-500 font-medium">Loading emergency details...</p>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="py-8">
        <button 
          onClick={() => navigate('/dashboard')}
          className="mb-6 flex items-center gap-2 text-gray-500 hover:text-gray-900 transition-colors font-medium"
        >
          <ArrowLeft className="w-5 h-5" />
          Back to Dashboard
        </button>
        <div className="bg-red-50 border border-red-200 p-6 rounded-2xl flex flex-col items-center text-center gap-4">
          <AlertCircle className="w-12 h-12 text-red-500" />
          <div>
            <h3 className="font-bold text-red-900 text-lg mb-1">Error Loading Details</h3>
            <p className="text-sm text-red-700">{error || 'Profile not found'}</p>
          </div>
          <button 
            onClick={() => window.location.reload()}
            className="mt-2 px-6 py-2 bg-red-100 hover:bg-red-200 text-red-800 font-semibold rounded-full transition-colors text-sm"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="py-4 space-y-6">
      <button 
        onClick={() => navigate('/dashboard')}
        className="flex items-center gap-2 text-gray-500 hover:text-gray-900 transition-colors font-medium"
      >
        <ArrowLeft className="w-5 h-5" />
        Back to Dashboard
      </button>

      <div className="bg-white rounded-2xl shadow-sm border border-red-100 overflow-hidden relative">
        <div className="h-2 w-full bg-red-500 absolute top-0 left-0"></div>
        
        <div className="p-6">
          <div className="flex items-start justify-between border-b border-gray-100 pb-5 mb-5">
            <div>
              <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Patient Name</p>
              <h2 className="text-2xl font-bold text-gray-900">{profile.full_name}</h2>
              {profile.phone_number && (
                <div className="flex items-center gap-2 mt-1.5 text-gray-600 font-medium">
                  <Phone className="w-4 h-4" />
                  <span>{profile.phone_number}</span>
                </div>
              )}
            </div>
            {profile.blood_group && (
              <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-2 flex flex-col items-center justify-center">
                <Droplet className="w-5 h-5 text-red-500 mb-1" />
                <span className="font-bold text-red-700 text-lg leading-none">{profile.blood_group}</span>
              </div>
            )}
          </div>

          <div className="space-y-5">
            <InfoSection 
              icon={<AlertCircle className="w-5 h-5 text-orange-500" />}
              title="Allergies"
              content={profile.allergies}
              emptyText="No known allergies"
              isHighPriority={true}
            />
            
            <InfoSection 
              icon={<Activity className="w-5 h-5 text-blue-500" />}
              title="Medical Conditions"
              content={profile.medical_conditions}
              emptyText="None reported"
            />
            
            <InfoSection 
              icon={<Pill className="w-5 h-5 text-purple-500" />}
              title="Medications"
              content={profile.medications}
              emptyText="None"
            />
            
            <InfoSection 
              icon={<Users className="w-5 h-5 text-green-500" />}
              title="Emergency Contacts"
              content={profile.emergency_contacts}
              emptyText="No contacts provided"
              isHighPriority={true}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function InfoSection({ 
  icon, 
  title, 
  content, 
  emptyText,
  isHighPriority = false
}: { 
  icon: React.ReactNode, 
  title: string, 
  content?: string,
  emptyText: string,
  isHighPriority?: boolean
}) {
  const containerClass = isHighPriority
    ? "bg-orange-50 rounded-xl p-3.5 border border-orange-100"
    : "bg-gray-50 rounded-xl p-3.5 border border-gray-100";
    
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-500 flex items-center gap-2 mb-2 uppercase tracking-wider">
        {icon}
        {title}
      </h3>
      <div className={containerClass}>
        {content ? (
          <p className="text-gray-900 whitespace-pre-wrap leading-relaxed font-medium">{content}</p>
        ) : (
          <p className="text-gray-400 italic">{emptyText}</p>
        )}
      </div>
    </div>
  );
}