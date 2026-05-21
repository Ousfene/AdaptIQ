import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import InternalLayout from '../components/InternalLayout';
import ConceptMastery from '../components/ConceptMastery';
import {
  Trophy,
  Target,
  Clock,
  Zap,
  BookOpen,
  Library,
  Flame,
  BarChart3,
  Loader2,
  Lock,
} from 'lucide-react';
import { RedisOpsStats, RoomProgress } from '../types';
import {
  fetchRedisOpsStats,
  fetchUserDailyTrend,
  fetchUserStats,
  fetchUserTopicBreakdown,
} from '../services/apiService';
import { UserStats } from '../types';

const FALLBACK_STATS: UserStats = {
  id: '',
  points: 0,
  level: '—',
  total_questions: 0,
  correct_questions: 0,
  global_accuracy: 0,
  daily_questions: 0,
  daily_correct: 0,
  daily_accuracy: 0,
  learning_time_minutes: 0,
};

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

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<UserStats | null>(null);
  const [statsError, setStatsError] = useState(false);
  const [topicBreakdown, setTopicBreakdown] = useState<Array<{
    topic: string;
    total_questions: number;
    correct_questions: number;
    accuracy: number;
    hints_used: number;
    avg_time_seconds: number;
  }>>([]);
  const [dailyTrend, setDailyTrend] = useState<Array<{
    date: string;
    total_questions: number;
    correct_questions: number;
    accuracy: number;
    avg_time_seconds: number;
  }>>([]);
  const [opsStats, setOpsStats] = useState<RedisOpsStats | null>(null);

  useEffect(() => {
    fetchUserStats()
      .then(setStats)
      .catch(() => {
        setStatsError(true);
        setStats(FALLBACK_STATS);
      });
  }, []);

  useEffect(() => {
    fetchUserTopicBreakdown()
      .then((payload) => setTopicBreakdown(payload.topics))
      .catch(() => setTopicBreakdown([]));

    fetchUserDailyTrend(7)
      .then((payload) => setDailyTrend(payload.days))
      .catch(() => setDailyTrend([]));

    fetchRedisOpsStats()
      .then(setOpsStats)
      .catch(() => setOpsStats(null));
  }, []);

  // Fallback placeholder while loading or on error
  const s = stats ?? FALLBACK_STATS;

  // Calculate streak from daily trend (consecutive days with activity from today going back)
  const calculateStreak = (): number => {
    if (dailyTrend.length === 0) return 0;
    
    // Sort by date descending to check from most recent
    const sortedDays = [...dailyTrend].sort((a, b) => 
      new Date(b.date).getTime() - new Date(a.date).getTime()
    );
    
    let streak = 0;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    for (let i = 0; i < sortedDays.length; i++) {
      const dayDate = new Date(sortedDays[i].date);
      dayDate.setHours(0, 0, 0, 0);
      
      // Expected date for streak continuation
      const expectedDate = new Date(today);
      expectedDate.setDate(today.getDate() - i);
      
      // Check if this day matches expected streak day and has activity
      if (dayDate.getTime() === expectedDate.getTime() && sortedDays[i].total_questions > 0) {
        streak++;
      } else if (i === 0 && sortedDays[i].total_questions === 0) {
        // Today has no activity yet, check from yesterday
        continue;
      } else {
        break; // Streak broken
      }
    }
    return streak;
  };

  const streak = calculateStreak();

  // Transform daily trend into weekly progress for the bar chart
  const weeklyProgress = (() => {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    
    // Create map of date -> questions
    const dateMap = new Map<string, number>();
    dailyTrend.forEach(d => {
      dateMap.set(d.date, d.total_questions);
    });
    
    // Get last 7 days
    const result = [];
    for (let i = 6; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      const dateStr = date.toISOString().split('T')[0];
      const dayName = days[date.getDay()];
      
      result.push({
        day: dayName,
        count: dateMap.get(dateStr) ?? 0
      });
    }
    return result;
  })();

  // Calculate max for bar chart scaling
  const maxQuestions = Math.max(...weeklyProgress.map(d => d.count), 10);

  // Dynamic room progress based on user stats
  const classicProgress = s.total_questions > 0 
    ? Math.min(100, Math.round((s.total_questions / 100) * 100)) // 100 questions = 100%
    : 0;
  
  // Challenge room unlocks after 5 classic questions
  const challengeUnlocked = s.total_questions >= 5;

  const rooms: RoomProgress[] = [
    {
      id: 'classic',
      name: 'Classic Room',
      description: 'The core learning environment. Adaptive difficulty and broad knowledge archives.',
      progress: classicProgress,
      isLocked: false,
      path: '/rooms/classic'
    },
    {
      id: 'challenge',
      name: 'Challenge Room',
      description: 'Ranked competition. Push your analytical boundaries to their absolute limits.',
      progress: 0,
      isLocked: !challengeUnlocked,
      path: '/rooms/challenge'
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
              <div className="text-[#F5F2E7] text-xl font-black font-playfair">{streak} Day Streak</div>
              <div className="text-[#D4AF37] text-[8px] font-bold uppercase tracking-widest">Consistency is Mastery</div>
            </div>
          </div>
        </div>
      </header>

      {statsError && (
        <div className="mb-8 p-4 bg-amber-50 border border-amber-200 text-amber-700 text-sm">
          Could not load live stats — showing cached totals.
        </div>
      )}

      <section className="mb-16">
        <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6 flex items-center gap-3">
          <Zap className="w-4 h-4 fill-current" /> Today's Rituals
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {!stats ? (
            <div className="col-span-4 flex justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-[#D4AF37]" />
            </div>
          ) : (
            <>
              <StatCard title="Questions" value={s.daily_questions} icon={<BookOpen className="w-5 h-5" />} />
              <StatCard title="Accuracy" value={`${s.daily_accuracy}%`} icon={<Target className="w-5 h-5" />} />
              <StatCard title="Time" value={`${s.learning_time_minutes}m`} icon={<Clock className="w-5 h-5" />} />
              <StatCard title="Points" value={s.points} icon={<Trophy className="w-5 h-5" />} subtext="Total earned" />
            </>
          )}
        </div>
      </section>

      <div className="grid lg:grid-cols-2 gap-10 mb-16">
        <section>
          <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6 flex items-center gap-3">
            <Target className="w-4 h-4" /> Topic Mastery
          </h2>
          <div className="bg-white p-6 border border-[#2D1B14]/10 shadow-sm space-y-5">
            {topicBreakdown.length === 0 ? (
              <p className="text-sm text-[#2D1B14]/60 italic">No topic data available yet.</p>
            ) : (
              topicBreakdown.map((item) => (
                <div key={item.topic} className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="font-black font-playfair text-[#2D1B14]">{item.topic}</span>
                    <span className="text-[#2D1B14]/70">{item.accuracy}%</span>
                  </div>
                  <div className="h-2 bg-[#2D1B14]/10 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#D4AF37]"
                      style={{ width: `${Math.max(0, Math.min(100, item.accuracy))}%` }}
                    />
                  </div>
                  <div className="text-xs text-[#2D1B14]/60">
                    {item.correct_questions}/{item.total_questions} correct | hints {item.hints_used} | avg {item.avg_time_seconds}s
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section>
          <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6 flex items-center gap-3">
            <BarChart3 className="w-4 h-4" /> Last 7 Days
          </h2>
          <div className="bg-white p-6 border border-[#2D1B14]/10 shadow-sm space-y-3">
            {dailyTrend.length === 0 ? (
              <p className="text-sm text-[#2D1B14]/60 italic">No recent trend data available yet.</p>
            ) : (
              dailyTrend.map((point) => (
                <div key={point.date} className="grid grid-cols-[80px_1fr_60px] items-center gap-3">
                  <span className="text-xs text-[#2D1B14]/70">{point.date.slice(5)}</span>
                  <div className="h-2 bg-[#2D1B14]/10 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#2D1B14]"
                      style={{ width: `${Math.max(0, Math.min(100, point.accuracy))}%` }}
                    />
                  </div>
                  <span className="text-xs text-right text-[#2D1B14]/70">{point.accuracy}%</span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <section className="mb-16">
        <h2 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6 flex items-center gap-3">
          <Library className="w-4 h-4" /> Redis Live Operations
        </h2>
        <div className="bg-white p-6 border border-[#2D1B14]/10 shadow-sm grid md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 border border-[#2D1B14]/10">
            <div className="text-[10px] uppercase tracking-widest opacity-50">Status</div>
            <div className="text-lg font-black font-playfair text-[#2D1B14]">{opsStats?.status ?? 'unavailable'}</div>
          </div>
          <div className="p-4 border border-[#2D1B14]/10">
            <div className="text-[10px] uppercase tracking-widest opacity-50">Active Sessions</div>
            <div className="text-lg font-black font-playfair text-[#2D1B14]">{opsStats?.active_sessions ?? 0}</div>
          </div>
          <div className="p-4 border border-[#2D1B14]/10">
            <div className="text-[10px] uppercase tracking-widest opacity-50">OTP Keys</div>
            <div className="text-lg font-black font-playfair text-[#2D1B14]">{opsStats?.otp_keys ?? 0}</div>
          </div>
          <div className="p-4 border border-[#2D1B14]/10">
            <div className="text-[10px] uppercase tracking-widest opacity-50">Rate-limit Keys</div>
            <div className="text-lg font-black font-playfair text-[#2D1B14]">{opsStats?.rate_limit_keys ?? 0}</div>
          </div>
        </div>
      </section>

      {/* Concept Mastery Section */}
      <section className="mb-16">
        <ConceptMastery />
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
                    style={{ height: `${maxQuestions > 0 ? (d.count / maxQuestions) * 140 : 0}px` }}
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
            {rooms.map(room => (
              <button
                key={room.id}
                onClick={() => !room.isLocked && room.path && navigate(room.path)}
                disabled={room.isLocked}
                className={`w-full text-left p-6 border border-[#2D1B14]/10 bg-white shadow-sm transition-all ${
                  room.isLocked 
                    ? 'opacity-50 cursor-not-allowed' 
                    : 'hover:border-[#D4AF37] hover:shadow-md cursor-pointer'
                }`}
              >
                <div className="flex justify-between items-center mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className="font-black font-playfair text-[#2D1B14]">{room.name}</h4>
                    {room.isLocked && <Lock className="w-4 h-4 text-[#2D1B14]/40" />}
                  </div>
                  <span className="text-[10px] font-bold text-[#D4AF37]">{room.progress}%</span>
                </div>
                <p className="text-xs text-[#2D1B14]/60 mb-3">{room.description}</p>
                <div className="w-full h-1 bg-[#2D1B14]/5 rounded-full overflow-hidden">
                  <div className="h-full bg-[#D4AF37]" style={{ width: `${room.progress}%` }} />
                </div>
                {room.isLocked && (
                  <p className="text-[10px] text-[#D4AF37] mt-2 italic">Complete 5 classic questions to unlock</p>
                )}
              </button>
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
              <span className="text-2xl font-black font-playfair text-[#D4AF37]">{s.level[0] ?? '?'}</span>
            </div>
            <div>
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">{s.level}</div>
              <div className="text-xs font-bold uppercase tracking-widest text-[#D4AF37]">Current Rank</div>
            </div>
          </div>
          
          <div className="flex gap-16">
            <div className="text-center">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">{s.total_questions}</div>
              <div className="text-[10px] font-bold uppercase tracking-widest opacity-40">Total Questions</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">{s.global_accuracy}%</div>
              <div className="text-[10px] font-bold uppercase tracking-widest opacity-40">Global Accuracy</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-black font-playfair text-[#2D1B14]">{s.points}</div>
              <div className="text-[10px] font-bold uppercase tracking-widest opacity-40">Total Points</div>
            </div>
          </div>
        </div>
      </section>
    </InternalLayout>
  );
};

export default Dashboard;
