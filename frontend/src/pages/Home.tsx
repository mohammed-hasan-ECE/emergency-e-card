import { Link } from 'react-router-dom';
import { Shield, Plus, UserCircle, AlertTriangle } from 'lucide-react';
import { storageService } from '../services/storage';

export function Home() {
  const hasProfile = !!storageService.getProfileId();

  return (
    <div className="flex flex-col gap-8 py-6">
      <div className="text-center space-y-4">
        <div className="mx-auto w-20 h-20 bg-brand-100 rounded-full flex items-center justify-center mb-6 shadow-sm">
          <Shield className="w-10 h-10 text-brand-600" />
        </div>
        <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">Emergency E-Card</h1>
        <p className="text-gray-500 max-w-sm mx-auto text-lg leading-relaxed">
          Critical medical information available instantly when every second counts.
        </p>
      </div>

      <div className="space-y-4 mt-4">
        {hasProfile ? (
          <Link
            to="/card"
            className="flex items-center gap-4 bg-white p-5 rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow group"
          >
            <div className="bg-blue-100 p-3 rounded-xl group-hover:scale-110 transition-transform">
              <UserCircle className="w-7 h-7 text-blue-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-lg text-gray-900">View My E-Card</h3>
              <p className="text-sm text-gray-500">Access your saved medical profile</p>
            </div>
          </Link>
        ) : (
          <Link
            to="/create"
            className="flex items-center gap-4 bg-white p-5 rounded-2xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow group"
          >
            <div className="bg-green-100 p-3 rounded-xl group-hover:scale-110 transition-transform">
              <Plus className="w-7 h-7 text-green-600" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-lg text-gray-900">Create E-Card</h3>
              <p className="text-sm text-gray-500">Set up your medical profile</p>
            </div>
          </Link>
        )}

        <Link
          to="/sos"
          className="flex items-center gap-4 bg-brand-600 p-5 rounded-2xl shadow-md hover:bg-brand-700 transition-colors group"
        >
          <div className="bg-white/20 p-3 rounded-xl group-hover:scale-110 transition-transform">
            <AlertTriangle className="w-7 h-7 text-white" />
          </div>
          <div className="flex-1">
            <h3 className="font-bold text-lg text-white">Trigger SOS</h3>
            <p className="text-brand-100 text-sm font-medium">Display emergency info instantly</p>
          </div>
        </Link>
      </div>

      <div className="mt-8 bg-blue-50 rounded-2xl p-6 border border-blue-100">
        <h4 className="font-semibold text-blue-900 mb-2 flex items-center gap-2">
          <Shield className="w-5 h-5" />
          Why create an E-Card?
        </h4>
        <ul className="space-y-2 text-sm text-blue-800">
          <li className="flex items-start gap-2">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full mt-1.5 shrink-0" />
            <span>Provides first responders with critical health data</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full mt-1.5 shrink-0" />
            <span>Lists allergies to prevent adverse drug reactions</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full mt-1.5 shrink-0" />
            <span>Ensures emergency contacts can be reached quickly</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
