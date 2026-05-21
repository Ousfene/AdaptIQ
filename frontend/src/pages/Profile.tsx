import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import InternalLayout from '../components/InternalLayout';
import ConceptMasterySection from '../components/profile/ConceptMasterySection';
import LearningStreakSection from '../components/profile/LearningStreakSection';
import ProfileHeader from '../components/profile/ProfileHeader';
import { API_BASE } from '../config';
import { getUserConceptMastery, ConceptMasteryItem } from '../services/customService';
import { authHeaders } from '../services/http';

interface ProfileUser {
  id: string;
  email: string;
  username: string;
  points: number;
  level: string;
  is_active: boolean;
  created_at: string;
}

interface ProfileStats {
  id: string;
  points: number;
  level: string;
  total_questions: number;
  global_accuracy: number;
  daily_questions: number;
  daily_accuracy: number;
  learning_time_minutes: number;
  daily_points: number;
  streak_days: number;
}

function formatMemberSince(createdAt: string): string {
  const parsed = new Date(createdAt);
  if (Number.isNaN(parsed.getTime())) {
    return 'Member since unknown';
  }

  return `Member since ${parsed.toLocaleString('en-US', { month: 'long', year: 'numeric' })}`;
}

// Render profile dashboard and load user/me plus concept mastery data.
export default function Profile() {
  const navigate = useNavigate();
  const [user, setUser] = useState<ProfileUser | null>(null);
  const [stats, setStats] = useState<ProfileStats | null>(null);
  const [concepts, setConcepts] = useState<ConceptMasteryItem[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch profile and mastery data for the current authenticated user.
    const loadProfile = async () => {
      const token = localStorage.getItem('adaptiq_token');
      const userId = localStorage.getItem('adaptiq_user_id') || localStorage.getItem('user_id');
      if (!token || !userId) {
        setError('You are not logged in.');
        setLoading(false);
        return;
      }

      try {
        const [meResponse, statsResponse, masteryResponse] = await Promise.all([
          fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() }),
          fetch(`${API_BASE}/api/auth/stats`, { headers: authHeaders() }),
          getUserConceptMastery(userId).catch(() => ({ concepts: [] as ConceptMasteryItem[] })),
        ]);

        const meData = await meResponse.json().catch(() => ({}));
        if (!meResponse.ok) {
          throw new Error(meData.detail ?? `HTTP ${meResponse.status}`);
        }

        const statsData = await statsResponse.json().catch(() => ({}));
        if (!statsResponse.ok) {
          throw new Error(statsData.detail ?? `HTTP ${statsResponse.status}`);
        }

        setUser(meData.user);
        setStats(statsData);
        setConcepts(masteryResponse.concepts || []);
      } catch (err: any) {
        setError(err.message ?? 'Failed to load profile.');
      } finally {
        setLoading(false);
      }
    };

    loadProfile();
  }, []);

  return (
    <InternalLayout>
      <button onClick={() => navigate('/dashboard')} className="mb-10 flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 transition-colors hover:text-[#D4AF37]">
        Back to Dashboard
      </button>

      <div className="mx-auto max-w-5xl space-y-8">
        <div>
          <h1 className="mb-3 text-4xl font-black text-[#2D1B14] font-playfair">Profile</h1>
          <p className="max-w-2xl text-sm text-[#2D1B14]/60">
            A learning archive that surfaces your current progress, streak, and concept mastery.
          </p>
        </div>

        {loading && (
          <div className="border border-[#2D1B14]/10 bg-white p-6 text-[#2D1B14]">Loading profile...</div>
        )}

        {!loading && error && (
          <div className="border border-red-200 bg-red-50 p-6 text-red-700">{error}</div>
        )}

        {!loading && user && (
          <div className="space-y-8">
            <ProfileHeader
              username={user.username}
              email={user.email}
              level={user.level}
              points={user.points}
              memberSince={formatMemberSince(user.created_at)}
            />

            <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
              <div className="border border-[#2D1B14]/10 bg-white p-5 shadow-sm">
                <div className="mb-1 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/55">Level</div>
                <div className="text-2xl font-black text-[#2D1B14] font-playfair">{user.level}</div>
              </div>
              <div className="border border-[#2D1B14]/10 bg-white p-5 shadow-sm">
                <div className="mb-1 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/55">Points</div>
                <div className="text-2xl font-black text-[#D4AF37] font-playfair">{user.points.toLocaleString()}</div>
              </div>
              <div className="border border-[#2D1B14]/10 bg-white p-5 shadow-sm">
                <div className="mb-1 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/55">Member Since</div>
                <div className="text-sm font-semibold text-[#2D1B14]">{formatMemberSince(user.created_at)}</div>
              </div>
              <div className="border border-[#2D1B14]/10 bg-white p-5 shadow-sm">
                <div className="mb-1 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/55">Status</div>
                <div className="text-sm font-semibold text-[#2D1B14]">{user.is_active ? 'Active learner' : 'Inactive'}</div>
              </div>
            </div>

            {stats && (
              <LearningStreakSection
                streakDays={stats.streak_days}
                dailyQuestions={stats.daily_questions}
                dailyAccuracy={stats.daily_accuracy}
                dailyPoints={stats.daily_points}
                learningTimeMinutes={stats.learning_time_minutes}
              />
            )}

            <ConceptMasterySection concepts={concepts} />
          </div>
        )}
      </div>
    </InternalLayout>
  );
}
