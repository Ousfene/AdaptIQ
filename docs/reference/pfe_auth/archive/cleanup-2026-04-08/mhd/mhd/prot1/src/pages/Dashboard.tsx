import React from 'react';
import { useNavigate } from 'react-router-dom';
import InternalLayout from '../components/InternalLayout';
import { 
  Trophy, 
  Target, 
  Clock, 
  Zap,
  ArrowRight,
  BookOpen,
  Lock,
  Library,
  Flame,
  BarChart3
} from 'lucide-react';
import { UserStats, RoomProgress } from '../types';

const StatCard: React.FC<{ title: string, value: string | number, icon: React.ReactNode, subtext?: string }> = ({ title, value, icon, subtext }) => (
  <div className="bg-white p-6 border border-[#2D1B14]/10 shadow-sm hover:shadow-md transition-shadow">
    <div className="flex items-center justify-between mb-4">
      <div className="text-[#D4AF37]">{icon}</div>
      <span className="text-[10px] font-bold uppercase tracking-widest opacity-40">{title}</span>
    </div>
    <div className="text-3xl font-black font-playfair text-[#2D1B14]">{value}</div>
    {subtext && <div className="text-xs italic text-[#2D1B14]/60 mt-1">{subtext}</div>}
  </div>
);

const RoomCard: React.FC<{ room: RoomProgress }> = ({ room }) => {
  const navigate = useNavigate();
  return (
    <div className={`relative group ${room.isLocked ? 'opacity-60' : ''}`}>
      <div className="bg-[#FDFCF7] p-8 border border-[#2D1B14]/10 hover:border-[#D4AF37]/50 transition-all duration-500 shadow-sm hover:shadow-xl flex flex-col h-full">
        <div className="flex justify-between items-start mb-6">
          <h3 className="text-2xl font-black font-playfair text-[#2D1B14]">{room.name}</h3>
          {room.isLocked ? <Lock className="w-5 h-5 text-[#2D1B14]/30" /> : <BookOpen className="w-5 h-5 text-[#D4AF37]" />}
        </div>
        <p className="text-[#2D1B14]/60 text-sm italic mb-8 flex-grow">{room.description}</p>
        
        <div className="space-y-4">
          <div className="flex justify-between items-end text-[10px] font-bold uppercase tracking-widest">
            <span>Progress</span>
            <span>{room.progress}%</span>
          </div>
          <div className="w-full h-1 bg-[#2D1B14]/5 rounded-full overflow-hidden">
            <div 
              className="h-full bg-[#D4AF37] transition-all duration-1000" 
              style={{ width: `${room.progress}%` }}
            />
          </div>
          
          <button 
            disabled={room.isLocked}
            onClick={() => navigate(`/rooms/${room.id}`)}
            className={`w-full py-3 text-[10px] font-bold uppercase tracking-[0.2em] flex items-center justify-center gap-2 transition-all ${
              room.isLocked 
                ? 'bg-[#2D1B14]/5 text-[#2D1B14]/30 cursor-not-allowed' 
                : 'bg-[#2D1B14] text-[#F5F2E7] hover:bg-[#3d261c]'
            }`}
          >
            {room.isLocked ? 'Locked' : 'Enter Room'} <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
};

const Dashboard: React.FC = () => {
  // Mock data - in a real app this would come from a backend/context
  const stats: UserStats = {
    id: '1',
    points: 1450,
    level: 'Explorer',
    totalQuestions: 340,
    globalAccuracy: 72,
    dailyQuestions: 24,
    dailyAccuracy: 78,
    learningTimeMinutes: 35
  };

  const weeklyProgress = [
    { day: 'Mon', count: 45 },
    { day: 'Tue', count: 32 },
    { day: 'Wed', count: 58 },
    { day: 'Thu', count: 24 },
    { day: 'Fri', count: 0 },
    { day: 'Sat', count: 0 },
    { day: 'Sun', count: 0 },
  ];

  const rooms: RoomProgress[] = [
    {
      id: 'classic',
      name: 'Classic Room',
      description: 'The core learning environment. Adaptive difficulty and broad knowledge archives.',
      progress: 42,
      isLocked: false
    },
    {
      id: 'challenge',
      name: 'Challenge Room',
      description: 'Harder difficulty. Push your analytical boundaries to their absolute limits.',
      progress: 0,
      isLocked: true
    },
    {
      id: 'exam',
      name: 'Exam Simulation',
      description: 'Timed sessions designed to mimic official scholarly evaluations.',
      progress: 0,
      isLocked: true
    }
  ];

  return (
    <InternalLayout>
      <header className="mb-12 flex justify-between items-end">
        <div>
          <h1 className="text-4xl font-black font-playfair text-[#2D1B14] mb-2">Welcome, Scholar</h1>
          <p className="text-[#2D1B14]/60 italic">Your intellectual legacy continues. The archives await.</p>
        </div>
        
        {/* Streak Note */}
        <div className="bg-[#2D1B14] p-4 border border-[#D4AF37] rotate-1 hover:rotate-0 transition-transform shadow-xl">
          <div className="flex items-center gap-3">
            <Flame className="text-[#D4AF37] w-6 h-6 fill-current animate-pulse" />
            <div>
              <div className="text-[#F5F2E7] text-xl font-black font-playfair">7 Day Streak</div>
              <div className="text-[#D4AF37] text-[8px] font-bold uppercase tracking-widest">Consistency is Mastery</div>
            </div>
          </div>
        </div>
      </header>

      <section className="mb-16">
        <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6 flex items-center gap-3">
          <Zap className="w-4 h-4 fill-current" /> Today's Rituals
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <StatCard title="Questions" value={stats.dailyQuestions} icon={<BookOpen className="w-5 h-5" />} />
          <StatCard title="Accuracy" value={`${stats.dailyAccuracy}%`} icon={<Target className="w-5 h-5" />} />
          <StatCard title="Time" value={`${stats.learningTimeMinutes}m`} icon={<Clock className="w-5 h-5" />} />
          <StatCard title="Points" value={`+${120}`} icon={<Trophy className="w-5 h-5" />} subtext="Earned today" />
        </div>
      </section>

      <div className="grid lg:grid-cols-3 gap-12 mb-16">
        {/* Weekly Progress */}
        <section className="lg:col-span-2">
          <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6 flex items-center gap-3">
            <BarChart3 className="w-4 h-4" /> Weekly Illumination
          </h2>
          <div className="bg-white p-8 border border-[#2D1B14]/10 shadow-sm h-64 flex items-end justify-between gap-2">
            {weeklyProgress.map((d, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-4">
                <div className="w-full relative group">
                  <div 
                    className="w-full bg-[#2D1B14]/5 group-hover:bg-[#D4AF37]/20 transition-colors rounded-t-sm" 
                    style={{ height: '140px' }}
                  />
                  <div 
                    className="absolute bottom-0 left-0 w-full bg-[#D4AF37] transition-all duration-1000 rounded-t-sm shadow-lg" 
                    style={{ height: `${(d.count / 60) * 140}px` }}
                  />
                  {/* Tooltip */}
                  <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-[#2D1B14] text-[#F5F2E7] text-[8px] px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap">
                    {d.count} Questions
                  </div>
                </div>
                <span className="text-[10px] font-bold uppercase tracking-widest opacity-40">{d.day}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Learning Rooms */}
        <section>
          <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6 flex items-center gap-3">
            <Library className="w-4 h-4" /> Active Rooms
          </h2>
          <div className="space-y-4">
            {rooms.slice(0, 2).map(room => (
              <div key={room.id} className={`p-6 border border-[#2D1B14]/10 bg-white shadow-sm ${room.isLocked ? 'opacity-50' : ''}`}>
                <div className="flex justify-between items-center mb-4">
                  <h4 className="font-black font-playfair text-[#2D1B14]">{room.name}</h4>
                  <span className="text-[10px] font-bold text-[#D4AF37]">{room.progress}%</span>
                </div>
                <div className="w-full h-1 bg-[#2D1B14]/5 rounded-full overflow-hidden">
                  <div className="h-full bg-[#D4AF37]" style={{ width: `${room.progress}%` }} />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section>
        <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6 flex items-center gap-3">
          <Trophy className="w-4 h-4" /> Overall Mastery
        </h2>
        <div className="bg-white p-10 border border-[#2D1B14]/10 shadow-sm flex flex-col md:flex-row justify-between items-center gap-10">
          <div className="flex items-center gap-6">
            <div className="w-20 h-20 rounded-full bg-[#2D1B14] flex items-center justify-center border-4 border-[#D4AF37] shadow-xl">
              <span className="text-2xl font-black font-playfair text-[#D4AF37]">{stats.level[0]}</span>
            </div>
            <div>
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">{stats.level}</div>
              <div className="text-xs font-bold uppercase tracking-widest text-[#D4AF37]">Current Rank</div>
            </div>
          </div>
          
          <div className="flex gap-16">
            <div className="text-center">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">{stats.totalQuestions}</div>
              <div className="text-[10px] font-bold uppercase tracking-widest opacity-40">Total Questions</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">{stats.globalAccuracy}%</div>
              <div className="text-[10px] font-bold uppercase tracking-widest opacity-40">Global Accuracy</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">{stats.points}</div>
              <div className="text-[10px] font-bold uppercase tracking-widest opacity-40">Total Points</div>
            </div>
          </div>
        </div>
      </section>
    </InternalLayout>
  );
};

export default Dashboard;
