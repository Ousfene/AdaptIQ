import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard,
  BookOpen,
  LogOut,
  Library,
  ChevronRight
} from 'lucide-react';

interface InternalLayoutProps {
  children: React.ReactNode;
}

const InternalLayout: React.FC<InternalLayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [isRoomsOpen, setIsRoomsOpen] = useState(true);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: <LayoutDashboard className="w-5 h-5" /> },
  ];

  const rooms = [
    { name: 'Classic Room', path: '/rooms/classic', id: 'classic' },
    { name: 'Challenge Room', path: '/rooms/challenge', id: 'challenge' },
  ];

  return (
    <div className="flex min-h-screen bg-[#F5F2E7] text-[#2D1B14] font-serif">
      {/* Sidebar */}
      <aside className="w-64 bg-[#2D1B14] text-[#F5F2E7] flex flex-col border-r border-[#D4AF37]/30">
        <div className="p-8 flex items-center gap-3 border-b border-[#D4AF37]/10">
          <div className="w-10 h-10 bg-[#D4AF37] rounded-sm flex items-center justify-center rotate-3">
            <Library className="text-[#2D1B14] w-6 h-6" />
          </div>
          <span className="text-xl font-black font-playfair tracking-tight">Adapti<span className="text-[#D4AF37]">Q</span></span>
        </div>

        {/* User display */}
        {user && (
          <div className="px-6 py-4 border-b border-[#D4AF37]/10">
            <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-1">Scholar</div>
            <div className="text-sm font-bold text-[#F5F2E7] truncate">{user.username}</div>
            <div className="text-[10px] text-[#F5F2E7]/40 truncate">{user.email}</div>
          </div>
        )}

        <nav className="flex-grow py-8 px-4 space-y-2">
          {navItems.map((item) => (
            <button
              key={item.name}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-4 px-4 py-3 rounded-sm transition-all duration-300 text-sm font-bold uppercase tracking-widest ${
                location.pathname === item.path
                  ? 'bg-[#D4AF37] text-[#2D1B14] shadow-lg'
                  : 'text-[#F5F2E7]/60 hover:text-[#F5F2E7] hover:bg-white/5'
              }`}
            >
              {item.icon}
              {item.name}
            </button>
          ))}

          <div>
            <button
              onClick={() => setIsRoomsOpen(!isRoomsOpen)}
              className="w-full flex items-center justify-between px-4 py-3 rounded-sm transition-all duration-300 text-sm font-bold uppercase tracking-widest text-[#F5F2E7]/60 hover:text-[#F5F2E7] hover:bg-white/5"
            >
              <div className="flex items-center gap-4">
                <BookOpen className="w-5 h-5" />
                <span>Rooms</span>
              </div>
              <ChevronRight className={`w-4 h-4 transition-transform duration-300 ${isRoomsOpen ? 'rotate-90' : ''}`} />
            </button>

            <div className={`overflow-hidden transition-all duration-500 ease-in-out ${isRoomsOpen ? 'max-h-48 opacity-100 mt-2' : 'max-h-0 opacity-0'}`}>
              <div className="pl-12 space-y-1">
                {rooms.map((room) => (
                  <button
                    key={room.id}
                    onClick={() => navigate(room.path)}
                    className={`w-full text-left py-2 text-[10px] font-bold uppercase tracking-[0.2em] transition-colors ${
                      location.pathname === room.path
                        ? 'text-[#D4AF37]'
                        : 'text-[#F5F2E7]/40 hover:text-[#F5F2E7]'
                    }`}
                  >
                    {room.name}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </nav>

        <div className="p-8 border-t border-[#D4AF37]/10">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-4 px-4 py-3 text-[#F5F2E7]/60 hover:text-[#D4AF37] transition-colors text-sm font-bold uppercase tracking-widest"
          >
            <LogOut className="w-5 h-5" />
            Logout
          </button>
        </div>
      </aside>

      <main className="flex-grow overflow-y-auto paper-texture">
        <div className="max-w-6xl mx-auto p-10">
          {children}
        </div>
      </main>
    </div>
  );
};

export default InternalLayout;
