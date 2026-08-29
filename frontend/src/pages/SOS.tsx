import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import type { SOSResponse } from '../types';
import { sosService } from '../services/api';
import { storageService } from '../services/storage';
import { ShieldAlert, AlertTriangle, Droplet, Home } from 'lucide-react';

export function SOS() {
  const [sosData, setSosData] = useState<SOSResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const triggerSOS = async () => {
      const profileId = storageService.getProfileId();
      
      if (!profileId) {
        setIsLoading(false);
        setError("No profile found. Please create an E-Card first.");
        return;
      }

      try {
        const data = await sosService.triggerSOS(profileId);
        setSosData(data);
      } catch (err: any) {
        console.error('Error triggering SOS:', err);
        setError('Failed to retrieve emergency information. Please check your connection.');
      } finally {
        setIsLoading(false);
      }
    };

    triggerSOS();
  }, []);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-6">
        <div className="w-24 h-24 bg-red-100 rounded-full flex items-center justify-center animate-pulse">
          <ShieldAlert className="w-12 h-12 text-red-600" />
        </div>
        <p className="text-xl font-bold text-red-600 animate-pulse">TRIGGERING SOS...</p>
      </div>
    );
  }

  if (error || !sosData) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-6 text-center px-4">
        <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center">
          <AlertTriangle className="w-10 h-10 text-red-600" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">SOS Action Failed</h2>
          <p className="text-gray-600 max-w-xs mx-auto">{error}</p>
        </div>
        <Link
          to="/"
          className="bg-gray-900 hover:bg-gray-800 text-white font-bold py-3 px-8 rounded-full transition-colors mt-4 flex items-center gap-2"
        >
          <Home className="w-5 h-5" />
          Return Home
        </Link>
      </div>
    );
  }

  return (
    <div className="py-2 animate-in fade-in duration-500">
      <div className="bg-red-600 text-white p-6 rounded-t-3xl text-center space-y-3 -mx-4 -mt-4 shadow-lg pb-10">
        <ShieldAlert className="w-16 h-16 mx-auto animate-pulse" />
        <h1 className="text-3xl font-black tracking-widest">{sosData.message.toUpperCase()}</h1>
        <p className="text-red-100 font-medium">EMERGENCY MEDICAL INFORMATION</p>
      </div>

      <div className="bg-white rounded-3xl shadow-xl -mt-6 p-6 space-y-6 relative z-10 border border-gray-100 min-h-[400px]">
        <div className="flex items-start justify-between pb-4 border-b border-gray-100">
          <div>
            <p className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-1">Patient Name</p>
            <h2 className="text-3xl font-bold text-gray-900">{sosData.full_name}</h2>
          </div>
          {sosData.blood_group && (
            <div className="bg-red-50 border-2 border-red-100 rounded-2xl px-5 py-3 flex flex-col items-center shadow-sm">
              <Droplet className="w-6 h-6 text-red-500 mb-1" />
              <span className="font-black text-red-700 text-2xl leading-none">{sosData.blood_group}</span>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <EmergencySection 
            title="ALLERGIES" 
            content={sosData.allergies} 
            isHighPriority={true}
          />
          
          <EmergencySection 
            title="MEDICAL CONDITIONS" 
            content={sosData.medical_conditions} 
            isHighPriority={false}
          />
          
          <EmergencySection 
            title="EMERGENCY CONTACTS" 
            content={sosData.emergency_contacts} 
            isHighPriority={true}
          />
        </div>
      </div>
    </div>
  );
}

function EmergencySection({ 
  title, 
  content, 
  isHighPriority 
}: { 
  title: string, 
  content: string, 
  isHighPriority: boolean 
}) {
  if (!content) return null;

  return (
    <div className={`p-4 rounded-2xl border-l-4 ${
      isHighPriority 
        ? 'bg-orange-50 border-orange-500' 
        : 'bg-blue-50 border-blue-500'
    }`}>
      <h3 className={`text-xs font-black uppercase tracking-wider mb-2 ${
        isHighPriority ? 'text-orange-800' : 'text-blue-800'
      }`}>
        {title}
      </h3>
      <p className="text-gray-900 font-bold text-lg whitespace-pre-wrap leading-snug">
        {content}
      </p>
    </div>
  );
}
