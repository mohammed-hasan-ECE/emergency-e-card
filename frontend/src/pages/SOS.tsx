import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import type { SOSResponse, NearbyUser, AcknowledgedResponder } from '../types';
import { profileService, sosService } from '../services/api';
import { storageService } from '../services/storage';
import { ShieldAlert, AlertTriangle, Droplet, Home, Loader2, CheckCircle } from 'lucide-react';

export function SOS() {
  const [sosData, setSosData] = useState<SOSResponse | null>(null);
  const [responders, setResponders] = useState<AcknowledgedResponder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isResolving, setIsResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const profileId = storageService.getProfileId();

  useEffect(() => {
    const triggerSOS = async () => {
      if (!profileId) {
        setIsLoading(false);
        setError("No profile found. Please create an E-Card first.");
        return;
      }

      try {
        const profile = await profileService.getProfile(profileId);

        if (!profile.latitude || !profile.longitude) {
          setError('Your current location is not available yet. Please try again.');
          setIsLoading(false);
          return;
        }

        const data = await sosService.triggerSOS(
          profileId,
          Number(profile.latitude),
          Number(profile.longitude)
        );

        setSosData(data);

        if (data.acknowledged_responders) {
          setResponders(data.acknowledged_responders);
        }
      } catch (err: any) {
        console.error('Error triggering SOS:', err);
        setError(
          err.response?.data?.detail ||
          'Failed to retrieve emergency information. Please check your connection.'
        );
      } finally {
        setIsLoading(false);
      }
    };

    triggerSOS();
  }, [profileId]);

  // WebSocket Connection for Sender
  useEffect(() => {
    if (!profileId) return;

    let ws: WebSocket;
    let reconnectTimeout: number | ReturnType<typeof setTimeout>;

    const connect = () => {
      const apiUrl = import.meta.env.VITE_API_URL || window.location.origin;
      const wsProtocol = apiUrl.startsWith('https') ? 'wss://' : 'ws://';
      const wsHost = apiUrl.replace(/^https?:\/\//, '');
      const wsUrl = `${wsProtocol}${wsHost}/ws/alerts/${profileId}`;

      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);

          if (payload.type === 'ALERT_RESPONDER_ACKNOWLEDGED') {
            const newResponder = {
              profile_id: payload.data.responder_profile_id,
              full_name: payload.data.responder_name,
              responder_phone: payload.data.responder_phone,
              status: payload.data.status
            };

            setResponders(prev => {
              if (prev.some(r => r.profile_id === newResponder.profile_id)) {
                return prev;
              }
              return [...prev, newResponder];
            });
          }
        } catch (err) {
          console.error("Failed to parse WebSocket message:", err);
        }
      };

      ws.onclose = () => {
        reconnectTimeout = setTimeout(connect, 3000); // Attempt reconnect after 3s
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) {
        ws.onclose = null; // Prevent reconnect on deliberate unmount cleanup
        ws.close();
      }
    };
  }, [profileId]);

  const handleEndSOS = async () => {
    if (!sosData || isResolving || !profileId) return;

    setIsResolving(true);
    try {
      await sosService.resolveAlert(sosData.alert_id, profileId);
      // Backend broadcasts ALERT_RESOLVED, UI will naturally reflect if needed,
      // but for the sender, we can manually navigate away or just let the UI sit in resolved state
      window.location.href = '/'; // Simple redirect back to home for the sender
    } catch (err) {
      console.error('Error ending SOS:', err);
      alert('Failed to end the emergency alert. Please try again.');
      setIsResolving(false);
    }
  };

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
            title="MEDICATIONS"
            content={sosData.medications}
            isHighPriority={false}
          />

          <EmergencySection
            title="Emergency Contact Name & Relationship"
            content={sosData.emergency_contacts}
            isHighPriority={true}
          />

          {sosData.emergency_contact_phone && (
            <EmergencySection
              title="Emergency Contact Phone"
              content={sosData.emergency_contact_phone}
              isHighPriority={true}
            />
          )}

          <div className="p-4 rounded-2xl bg-blue-50 border border-blue-200">
            <h3 className="text-xs font-black uppercase tracking-wider mb-3 text-blue-800 flex items-center justify-between">
              <span>Responders coming to help: {responders.length}</span>
            </h3>

            {responders.length === 0 ? (
              <p className="text-blue-600 text-sm font-medium italic">
                Waiting for someone to respond...
              </p>
            ) : (
              <div className="space-y-3">
                {responders.map((responder) => (
                  <div
                    key={responder.profile_id}
                    className="flex items-center gap-3 bg-white rounded-xl p-3 border border-blue-100 shadow-sm"
                  >
                    <div className="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]"></div>
                    <div>
                      <p className="font-bold text-gray-900 leading-tight">
                        {responder.full_name}
                      </p>
                      {responder.responder_phone && (
                        <p className="text-sm font-medium text-gray-700">
                          {responder.responder_phone}
                        </p>
                      )}
                      <p className="text-sm text-blue-600 font-medium mt-0.5">
                        On the way
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {sosData.nearby_users && sosData.nearby_users.length > 0 && (
            <div className="p-4 rounded-2xl bg-green-50 border border-green-200">
              <h3 className="text-xs font-black uppercase tracking-wider mb-3 text-green-800">
                NEARBY RESPONDERS
              </h3>

              <div className="space-y-3">
                {sosData.nearby_users.map((user: NearbyUser) => (
                  <div
                    key={user.profile_id}
                    className="flex items-center justify-between bg-white rounded-xl p-3 border border-green-100"
                  >
                    <div>
                      <p className="font-bold text-gray-900">
                        {user.full_name}
                      </p>
                      <p className="text-sm text-gray-500">
                        {user.distance_km} km away
                      </p>
                    </div>

                    <span className="text-xs font-bold text-green-700 bg-green-100 px-3 py-1 rounded-full">
                      NEARBY
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="pt-4">
             <button
                onClick={handleEndSOS}
                disabled={isResolving}
                className="w-full bg-red-50 hover:bg-red-100 text-red-700 font-bold py-4 px-4 rounded-2xl flex items-center justify-center gap-2 transition-colors disabled:opacity-50 border border-red-200"
              >
                {isResolving ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <CheckCircle className="w-5 h-5" />
                )}
                End SOS (I'm Safe)
              </button>
          </div>
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
