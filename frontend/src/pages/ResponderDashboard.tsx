import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { storageService } from '../services/storage';
import { sosService } from '../services/api';
import type { NearbyAlert } from '../types';
import { 
  ShieldAlert, MapPin, Loader2, AlertCircle, 
  RefreshCw, User, Plus, Activity
} from 'lucide-react';

export function ResponderDashboard() {
  const [alerts, setAlerts] = useState<NearbyAlert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  
  const profileId = storageService.getProfileId();

  const fetchAlerts = useCallback(async (showRefreshIndicator = false) => {
    if (!profileId) {
      setIsLoading(false);
      return;
    }

    if (showRefreshIndicator) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    setError(null);

    try {
      const data = await sosService.getNearbyAlerts(profileId);
      setAlerts(data.nearby_alerts || []);
    } catch (err: any) {
      console.error('Error fetching nearby alerts:', err);
      setError('Could not load nearby alerts. Please check your connection.');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [profileId]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  if (!profileId) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-6 text-center">
        <div className="w-20 h-20 bg-gray-100 rounded-full flex items-center justify-center">
          <User className="w-10 h-10 text-gray-400" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Profile Required</h2>
          <p className="text-gray-500 max-w-[250px] mx-auto">
            You must create an Emergency E-Card before viewing the responder dashboard.
          </p>
        </div>
        <Link
          to="/create"
          className="bg-brand-600 hover:bg-brand-700 text-white font-bold py-3 px-8 rounded-full transition-colors shadow-sm flex items-center gap-2 mt-4"
        >
          <Plus className="w-5 h-5" />
          Create E-Card
        </Link>
      </div>
    );
  }

  return (
    <div className="py-4 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Activity className="w-6 h-6 text-brand-600" />
            Nearby Alerts
          </h1>
          <p className="text-sm text-gray-500 mt-1">Active emergencies in your area</p>
        </div>
        <button
          onClick={() => fetchAlerts(true)}
          disabled={isLoading || isRefreshing}
          className="p-2.5 text-gray-500 hover:text-brand-600 bg-gray-100 hover:bg-brand-50 rounded-full transition-colors disabled:opacity-50"
          aria-label="Refresh alerts"
        >
          <RefreshCw className={`w-5 h-5 ${isRefreshing ? 'animate-spin text-brand-600' : ''}`} />
        </button>
      </div>

      {isLoading && !isRefreshing ? (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <Loader2 className="w-10 h-10 text-brand-500 animate-spin" />
          <p className="text-gray-500 font-medium">Scanning for alerts...</p>
        </div>
      ) : error ? (
        <div className="bg-red-50 border border-red-200 p-6 rounded-2xl flex flex-col items-center text-center gap-4">
          <AlertCircle className="w-12 h-12 text-red-500" />
          <div>
            <h3 className="font-bold text-red-900 text-lg mb-1">Error Loading Alerts</h3>
            <p className="text-sm text-red-700">{error}</p>
          </div>
          <button 
            onClick={() => fetchAlerts()}
            className="mt-2 px-6 py-2 bg-red-100 hover:bg-red-200 text-red-800 font-semibold rounded-full transition-colors text-sm"
          >
            Try Again
          </button>
        </div>
      ) : alerts.length === 0 ? (
        <div className="bg-white border border-gray-100 rounded-2xl p-8 flex flex-col items-center text-center gap-4 shadow-sm">
          <div className="w-16 h-16 bg-green-50 rounded-full flex items-center justify-center">
            <ShieldAlert className="w-8 h-8 text-green-500" />
          </div>
          <div>
            <h3 className="font-bold text-gray-900 text-lg mb-1">No Active Alerts</h3>
            <p className="text-sm text-gray-500">There are no reported emergencies in your immediate vicinity right now.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {alerts.map((alert) => (
            <Link
              to={`/emergency/${alert.profile_id}`}
              key={alert.alert_id} 
              className="block bg-white border border-red-100 rounded-2xl p-5 shadow-sm relative overflow-hidden hover:shadow-md hover:border-red-300 transition-all cursor-pointer group"
            >
              <div className="absolute top-0 left-0 w-1.5 h-full bg-red-500 group-hover:bg-red-600 transition-colors"></div>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold text-gray-900 text-lg group-hover:text-red-700 transition-colors">
                    {alert.full_name || 'Unknown User'}
                  </h3>
                  <div className="flex items-center gap-1.5 text-gray-500 text-sm mt-1">
                    <MapPin className="w-4 h-4 text-red-500" />
                    <span>{alert.distance_km.toFixed(2)} km away</span>
                  </div>
                </div>
                <div className="bg-red-50 text-red-700 text-xs font-bold px-3 py-1.5 rounded-full flex items-center gap-1.5 animate-pulse">
                  <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                  ACTIVE
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
