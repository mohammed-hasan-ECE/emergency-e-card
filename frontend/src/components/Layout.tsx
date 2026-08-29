import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { HeartPulse, Home, PlusCircle, User, AlertCircle } from 'lucide-react';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  
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
        </div>
      </footer>
    </div>
  );
}
