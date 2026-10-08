import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import type { TrackInfo } from '../types';
import { trackingService } from '../services/api';
import {
  ShieldAlert, MapPin, Clock, ExternalLink,
  AlertTriangle, Loader2, HeartPulse,
} from 'lucide-react';

const POLL_INTERVAL_MS = 10000;

function formatAge(updatedAt: string | null): string {
  if (!updatedAt) return 'unknown time';
  const seconds = Math.max(0, Math.round((Date.now() - new Date(updatedAt).getTime()) / 1000));
  if (seconds < 60) return `${seconds} second${seconds === 1 ? '' : 's'} ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hour${hours === 1 ? '' : 's'} ago`;
}

export function TrackPage() {
  const { token } = useParams<{ token: string }>();
  const [track, setTrack] = useState<TrackInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [, setTick] = useState(0);

  const fetchTracking = useCallback(async () => {
    if (!token) {
      setError('This tracking link is invalid.');
      setIsLoading(false);
      return;
    }

    try {
      const data = await trackingService.getTracking(token);
      setTrack(data);
      setError(null);
    } catch (err: any) {
      if (err.response?.status === 410) {
        setError('Tracking has ended. The emergency is over or the link has expired.');
      } else if (err.response?.status === 404) {
        setError('This tracking link was not found. It may be incorrect or expired.');
      } else if (err.response?.status === 429) {
        setError('Too many requests. Please wait a moment and refresh.');
      } else {
        setError('Could not load tracking information. Please check your connection.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchTracking();
    const interval = setInterval(fetchTracking, POLL_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        fetchTracking();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    // Re-render the relative "updated … ago" label on each poll cycle.
    const ticker = setInterval(() => setTick((t) => t + 1), POLL_INTERVAL_MS);
    return () => {
      clearInterval(interval);
      clearInterval(ticker);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchTracking]);

  // Keep this unauthenticated page out of search indexes and strip
  // referrers so the token-bearing URL never leaks to third parties.
  useEffect(() => {
    const robots = document.createElement('meta');
    robots.name = 'robots';
    robots.content = 'noindex, nofollow';
    document.head.appendChild(robots);
    const referrer = document.createElement('meta');
    referrer.name = 'referrer';
    referrer.content = 'no-referrer';
    document.head.appendChild(referrer);
    return () => {
      document.head.removeChild(robots);
      document.head.removeChild(referrer);
    };
  }, []);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-4">
        <Loader2 className="w-10 h-10 text-brand-500 animate-spin" />
        <p className="text-gray-500 font-medium">Loading emergency tracking…</p>
      </div>
    );
  }

  if (error || !track) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-6 text-center px-4">
        <div className="w-20 h-20 bg-gray-100 rounded-full flex items-center justify-center">
          <AlertTriangle className="w-10 h-10 text-gray-400" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Tracking Unavailable</h2>
          <p className="text-gray-600 max-w-xs mx-auto">{error}</p>
        </div>
        <Link
          to="/"
          className="bg-gray-900 hover:bg-gray-800 text-white font-bold py-3 px-8 rounded-full transition-colors mt-4"
        >
          Return Home
        </Link>
      </div>
    );
  }

  const isLive = track.location_status === 'current';
  const isStale = track.location_status === 'stale';

  return (
    <div className="py-2 animate-in fade-in duration-500">
      <div className="bg-red-600 text-white p-6 rounded-t-3xl text-center space-y-3 -mx-4 -mt-4 shadow-lg pb-10">
        <ShieldAlert className="w-16 h-16 mx-auto animate-pulse" />
        <h1 className="text-3xl font-black tracking-widest">EMERGENCY TRACKING</h1>
        <p className="text-red-100 font-medium">{track.person_name} NEEDS URGENT HELP</p>
      </div>

      <div className="bg-white rounded-3xl shadow-xl -mt-6 p-6 space-y-6 relative z-10 border border-gray-100">
        <div className={`p-4 rounded-2xl border-l-4 flex items-center gap-3 ${
          isLive
            ? 'bg-green-50 border-green-500'
            : isStale
              ? 'bg-orange-50 border-orange-500'
              : 'bg-gray-50 border-gray-400'
        }`}>
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
            isLive ? 'bg-green-500 animate-pulse' : isStale ? 'bg-orange-500' : 'bg-gray-400'
          }`} />
          <div>
            <p className="font-bold text-gray-900">
              {isLive ? 'Live location' : isStale ? 'Last known location' : 'Location unavailable'}
            </p>
            <p className="text-sm text-gray-500 flex items-center gap-1">
              <Clock className="w-4 h-4" />
              Last updated {formatAge(track.location_updated_at)}
            </p>
          </div>
        </div>

        {track.has_location && track.map_embed_url ? (
          <div className="rounded-2xl overflow-hidden border border-gray-200 shadow-sm">
            <iframe
              title={`Emergency location map for ${track.person_name}`}
              src={track.map_embed_url}
              referrerPolicy="no-referrer"
              className="w-full h-72 border-0"
              loading="lazy"
            />
          </div>
        ) : (
          <div className="p-4 rounded-2xl bg-gray-50 border border-gray-200 text-center">
            <MapPin className="w-8 h-8 text-gray-400 mx-auto mb-2" />
            <p className="text-gray-600 font-medium">
              No location is currently available. Please try again shortly.
            </p>
          </div>
        )}

        {track.maps_url && (
          <a
            href={track.maps_url}
            target="_blank"
            rel="noopener noreferrer"
            referrerPolicy="no-referrer"
            className="w-full bg-brand-600 hover:bg-brand-700 text-white font-bold py-4 px-4 rounded-2xl transition-colors flex items-center justify-center gap-2"
          >
            <MapPin className="w-5 h-5" />
            Open in Google Maps
            <ExternalLink className="w-4 h-4" />
          </a>
        )}

        <div className="flex items-center justify-center gap-2 text-gray-400 text-xs pt-2">
          <HeartPulse className="w-4 h-4" />
          <span>Emergency E-Card live tracking</span>
        </div>
      </div>
    </div>
  );
}
