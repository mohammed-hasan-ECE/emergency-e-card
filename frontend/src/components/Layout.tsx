import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { profileService } from '../services/api';
import { storageService } from '../services/storage';
import { HeartPulse, Home, PlusCircle, User, AlertCircle, Activity } from 'lucide-react';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const lastLocationUpdateRef = useRef(0);

  useEffect(() => {
    // Never run device tracking on the public tracking page.
    if (location.pathname.startsWith('/track')) {
      return;
    }

    if (!navigator.geolocation) {
      return;
    }

    // One-time bootstrap: existing devices created before publish tokens
    // existed pair exactly once via rotation, then store the raw token.
    const bootstrapToken = async () => {
      const currentProfileId = storageService.getProfileId();

      if (!currentProfileId || storageService.getLocationPublishToken()) {
        return;
      }

      try {
        const profile = await profileService.getProfile(currentProfileId);

        if (!profile.phone_number) {
          return;
        }

        const rotated = await profileService.rotateLocationToken(
          currentProfileId,
          profile.phone_number
        );

        if (rotated.location_publish_token) {
          storageService.setLocationPublishToken(rotated.location_publish_token);
        }
      } catch (err) {
        // Silent backoff: retry on next app start. Never blocks the UI.
        console.error('Failed to bootstrap location token:', err);
      }
    };

    bootstrapToken();

    const watchId = navigator.geolocation.watchPosition(
      async (position) => {
        const currentProfileId = storageService.getProfileId();

        if (!currentProfileId) {
          return;
        }

        const now = Date.now();

        // Avoid sending location updates more than once every 5 seconds.
        if (now - lastLocationUpdateRef.current < 5000) {
          return;
        }

        lastLocationUpdateRef.current = now;

        const publishToken = storageService.getLocationPublishToken();

        if (!publishToken) {
          // No publish token yet (bootstrap pending): skip rather than
          // sending an unauthenticated update.
          return;
        }

        try {
          await profileService.updateProfileLocation(
            currentProfileId,
            position.coords.latitude,
            position.coords.longitude,
            publishToken
          );
        } catch (err) {
          console.error('Failed to update live location:', err);
        }
      },
      (err) => {
        console.error('Live location error:', err);
      },
      {
        enableHighAccuracy: true,
        maximumAge: 5000,
        timeout: 10000,
      }
    );

    return () => {
      navigator.geolocation.clearWatch(watchId);
    };
  }, []);
  
  const isActive = (path: string) => {
    return location.pathname === path ? 'text-brand-600' : 'text-gray-500 hover:text-gray-900';
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white shadow-sm sticky top-0 z-10">
        <div className="max-w-md mx-auto px-4 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="bg-brand-500 p-1.5 rounded-lg">
              <HeartPulse className="w-6 h-6 text-white" />
            </div>
            <span className="font-bold text-xl text-gray-900">E-Card</span>
          </Link>
          
          <Link 
            to="/sos" 
            className="flex items-center gap-1 bg-brand-600 hover:bg-brand-700 text-white px-3 py-1.5 rounded-full font-bold text-sm transition-colors shadow-sm"
          >
            <AlertCircle className="w-4 h-4" />
            <span>SOS</span>
          </Link>
        </div>
      </header>

      <main className="flex-1 w-full max-w-md mx-auto p-4 pb-24">
        {children}
      </main>

      <footer className="bg-white border-t border-gray-200 fixed bottom-0 w-full z-10 pb-safe">
        <div className="max-w-md mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className={`flex flex-col items-center gap-1 ${isActive('/')}`}>
            <Home className="w-6 h-6" />
            <span className="text-[10px] font-medium">Home</span>
          </Link>
          
          <Link to="/create" className={`flex flex-col items-center gap-1 ${isActive('/create')}`}>
            <PlusCircle className="w-6 h-6" />
            <span className="text-[10px] font-medium">Create</span>
          </Link>
          
          <Link to="/card" className={`flex flex-col items-center gap-1 ${isActive('/card')}`}>
            <User className="w-6 h-6" />
            <span className="text-[10px] font-medium">My Card</span>
          </Link>

          <Link to="/dashboard" className={`flex flex-col items-center gap-1 ${isActive('/dashboard')}`}>
            <Activity className="w-6 h-6" />
            <span className="text-[10px] font-medium">Alerts</span>
          </Link>
        </div>
      </footer>
    </div>
  );
}
