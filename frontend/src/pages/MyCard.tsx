import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Profile } from '../types';
import { profileService } from '../services/api';
import { storageService } from '../services/storage';
import { 
  User, Phone, Droplet, AlertCircle, Activity, 
  Pill, Users, Loader2, Edit3, Plus, ShieldAlert 
} from 'lucide-react';

export function MyCard() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchProfile = async () => {
      const profileId = storageService.getProfileId();
      
      if (!profileId) {
        setIsLoading(false);
        return;
      }

      try {
        const data = await profileService.getProfile(profileId);
        setProfile(data);
      } catch (err: any) {
        console.error('Error fetching profile:', err);
        setError('Could not load your profile. It may have been deleted or there is a network issue.');
        if (err.response?.status === 404) {
           storageService.clearProfileId();
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, []);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <Loader2 className="w-10 h-10 text-brand-500 animate-spin" />
        <p className="text-gray-500 font-medium">Loading your E-Card...</p>
      </div>
    );
  }

  if (!profile && !error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-6 text-center">
        <div className="w-20 h-20 bg-gray-100 rounded-full flex items-center justify-center">
          <User className="w-10 h-10 text-gray-400" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">No Profile Found</h2>
          <p className="text-gray-500 max-w-[250px] mx-auto">
            You haven't created an Emergency E-Card yet.
          </p>
        </div>
        <Link
          to="/create"
          className="bg-brand-600 hover:bg-brand-700 text-white font-bold py-3 px-8 rounded-full transition-colors shadow-sm flex items-center gap-2 mt-4"
        >
          <Plus className="w-5 h-5" />
          Create E-Card Now
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-8">
        <div className="bg-red-50 border border-red-200 p-6 rounded-2xl flex flex-col items-center text-center gap-4">
          <AlertCircle className="w-12 h-12 text-red-500" />
          <div>
            <h3 className="font-bold text-red-900 text-lg mb-1">Error Loading Profile</h3>
            <p className="text-sm text-red-700">{error}</p>
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Medical Profile</h1>
        <Link 
          to="/edit" 
          className="p-2 text-gray-500 hover:text-brand-600 bg-gray-100 hover:bg-brand-50 rounded-full transition-colors"
        >
          <Edit3 className="w-5 h-5" />
        </Link>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden relative">
        <div className="h-2 w-full bg-brand-500 absolute top-0 left-0"></div>
        
        <div className="p-6">
          <div className="flex items-start justify-between border-b border-gray-100 pb-5 mb-5">
            <div>
              <h2 className="text-2xl font-bold text-gray-900">{profile?.full_name}</h2>
              <div className="flex items-center gap-2 mt-1.5 text-gray-600 font-medium">
                <Phone className="w-4 h-4" />
                <span>{profile?.phone_number}</span>
              </div>
            </div>
            {profile?.blood_group && (
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
              content={profile?.allergies}
              emptyText="No known allergies"
            />
            
            <InfoSection 
              icon={<Activity className="w-5 h-5 text-blue-500" />}
              title="Medical Conditions"
              content={profile?.medical_conditions}
              emptyText="None reported"
            />
            
            <InfoSection 
              icon={<Pill className="w-5 h-5 text-purple-500" />}
              title="Medications"
              content={profile?.medications}
              emptyText="None"
            />
            
            <InfoSection 
              icon={<Users className="w-5 h-5 text-green-500" />}
              title="Emergency Contacts"
              content={profile?.emergency_contacts}
              emptyText="No contacts provided"
            />
          </div>
        </div>
      </div>
      
      <button
        onClick={() => navigate('/sos')}
        className="w-full bg-red-600 hover:bg-red-700 text-white font-bold py-4 px-4 rounded-2xl shadow-md transition-colors flex items-center justify-center gap-3 active:scale-[0.98]"
      >
        <ShieldAlert className="w-6 h-6" />
        <span className="text-lg">TRIGGER SOS</span>
      </button>
    </div>
  );
}

function InfoSection({ 
  icon, 
  title, 
  content, 
  emptyText 
}: { 
  icon: React.ReactNode, 
  title: string, 
  content?: string,
  emptyText: string
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-500 flex items-center gap-2 mb-2 uppercase tracking-wider">
        {icon}
        {title}
      </h3>
      <div className="bg-gray-50 rounded-xl p-3.5 border border-gray-100">
        {content ? (
          <p className="text-gray-900 whitespace-pre-wrap leading-relaxed">{content}</p>
        ) : (
          <p className="text-gray-400 italic">{emptyText}</p>
        )}
      </div>
    </div>
  );
}
