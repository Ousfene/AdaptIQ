import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import InternalLayout from '../components/InternalLayout';
import {
  ArrowLeft,
  User,
  TrendingUp,
  BookOpen,
  Zap,
  Trophy,
  Loader2,
  AlertTriangle,
  Target,
  Award,
} from 'lucide-react';
import { fetchUserStats, fetchConceptMastery, getChallengeStatus, fetchUserTopicBreakdown, fetchUserDailyTrend } from '../services/apiService';
import { ConceptMastery, ConceptBreakdown, UserStats, ChallengeStatus } from '../types';

interface ThumbSize {
  width: number;
  height: number;
}

/**
 * Get color class for theta value.
 * Matches backend thresholds in routers/auth.py:341-346:
 *   theta < -1.0: Beginner (red)
 *   theta < 1.0:  Intermediate (yellow)
 *   theta >= 1.0: Advanced (green)
 */
const getThetaColor = (theta: number): string => {
  if (theta < -1.0) return 'bg-red-500';      // Beginner
  if (theta < 1.0) return 'bg-yellow-500';    // Intermediate
  return 'bg-green-500';                       // Advanced
};

/**
 * Get label for theta value.
 * Matches backend thresholds in routers/auth.py:341-346.
 */
const getThetaLabel = (theta: number): string => {
  if (theta < -1.0) return 'Beginner';
  if (theta < 1.0) return 'Intermediate';
  return 'Advanced';
};

const Profile: React.FC = () => {
  const navigate = useNavigate();
  const [userStats, setUserStats] = useState<UserStats | null>(null);
  const [conceptMastery, setConceptMastery] = useState<ConceptBreakdown | null>(null);
  const [challengeStatus, setChallengeStatus] = useState<ChallengeStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [stats, concepts, challenge] = await Promise.all([
          fetchUserStats(),
          fetchConceptMastery(),
          getChallengeStatus(),
        ]);
        setUserStats(stats);
        setConceptMastery(concepts);
        setChallengeStatus(challenge);
      } catch (err: any) {
        setError(err.message || 'Failed to load profile data');
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, []);

  if (isLoading) {
    return (
      <InternalLayout>
        <div className="flex items-center justify-center gap-3 text-[#D4AF37] font-bold uppercase tracking-widest">
          <Loader2 className="w-6 h-6 animate-spin" /> Loading Profile...
        </div>
      </InternalLayout>
    );
  }

  if (error || !userStats) {
    return (
      <InternalLayout>
        <button onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 hover:text-[#D4AF37] mb-12 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </button>
        <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 text-red-700">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <span>{error || 'Failed to load profile'}</span>
        </div>
      </InternalLayout>
    );
  }

  // Calculate mastery by topic
  const masteryByTopic: Record<string, ConceptMastery[]> = conceptMastery?.concepts || {};
  const topicList = Object.keys(masteryByTopic);

  return (
    <InternalLayout>
      <button onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 hover:text-[#D4AF37] mb-12 transition-colors">
        <ArrowLeft className="w-4 h-4" /> Back to Dashboard
      </button>

      <div className="max-w-5xl mx-auto">
        {/* Profile Header */}
        <div className="mb-16">
          <div className="flex items-start gap-8">
            <div className="w-24 h-24 bg-gradient-to-br from-[#D4AF37]/20 to-[#D4AF37]/5 rounded-lg flex items-center justify-center border-2 border-[#D4AF37]/40">
              <User className="w-12 h-12 text-[#D4AF37]" />
            </div>

            <div className="flex-1">
              <div className="text-xs font-bold uppercase tracking-widest text-[#D4AF37] mb-2">User Profile</div>
              <h1 className="text-4xl font-black font-playfair text-[#2D1B14] mb-6">{userStats.id}</h1>

              <div className="grid grid-cols-4 gap-4">
                <div className="p-4 bg-white border border-[#2D1B14]/10">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-1">Level</div>
                  <div className="text-2xl font-black text-[#2D1B14]">{userStats.level}</div>
                </div>
                <div className="p-4 bg-white border border-[#2D1B14]/10">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-1">Points</div>
                  <div className="text-2xl font-black text-[#D4AF37]">{userStats.points}</div>
                </div>
                <div className="p-4 bg-white border border-[#2D1B14]/10">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-1">Total Questions</div>
                  <div className="text-2xl font-black text-[#2D1B14]">{userStats.total_questions}</div>
                </div>
                <div className="p-4 bg-white border border-[#2D1B14]/10">
                  <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-1">Accuracy</div>
                  <div className="text-2xl font-black text-green-600">{Math.round(userStats.global_accuracy)}%</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Challenge Status */}
        {challengeStatus && (
          <div className="mb-16 p-8 bg-gradient-to-r from-[#D4AF37]/10 to-[#D4AF37]/5 border-2 border-[#D4AF37]/40">
            <div className="flex items-center gap-3 mb-6">
              <Trophy className="w-6 h-6 text-[#D4AF37]" />
              <h2 className="text-2xl font-black font-playfair text-[#2D1B14]">Challenge Rank</h2>
            </div>

            <div className="grid grid-cols-4 gap-4">
              <div>
                <div className="text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-2">Current Rank</div>
                <div className="text-lg font-bold text-[#D4AF37]">{challengeStatus.current_rank.name}</div>
              </div>
              <div>
                <div className="text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-2">Wins</div>
                <div className="text-lg font-bold text-green-600">{challengeStatus.wins}</div>
              </div>
              <div>
                <div className="text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-2">Losses</div>
                <div className="text-lg font-bold text-red-600">{challengeStatus.losses}</div>
              </div>
              <div>
                <div className="text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-2">Win Rate</div>
                <div className="text-lg font-bold text-[#2D1B14]">
                  {challengeStatus.wins + challengeStatus.losses > 0
                    ? Math.round((challengeStatus.wins / (challengeStatus.wins + challengeStatus.losses)) * 100)
                    : 0}%
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Stats Overview */}
        <div className="mb-16">
          <h2 className="text-2xl font-black font-playfair text-[#2D1B14] mb-6 flex items-center gap-3">
            <TrendingUp className="w-6 h-6 text-[#D4AF37]" /> Learning Statistics
          </h2>

          <div className="grid grid-cols-2 gap-6">
            <div className="p-6 bg-white border border-[#2D1B14]/10">
              <div className="text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-3">Daily Statistics</div>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-[#2D1B14]/70">Questions Today</span>
                  <span className="font-bold text-[#2D1B14]">{userStats.daily_questions}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#2D1B14]/70">Correct Today</span>
                  <span className="font-bold text-green-600">{userStats.daily_correct}</span>
                </div>
                <div className="flex justify-between border-t border-[#2D1B14]/10 pt-3">
                  <span className="text-[#2D1B14]/70">Today's Accuracy</span>
                  <span className="font-bold text-[#2D1B14]">{Math.round(userStats.daily_accuracy)}%</span>
                </div>
              </div>
            </div>

            <div className="p-6 bg-white border border-[#2D1B14]/10">
              <div className="text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-3">All-Time Statistics</div>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-[#2D1B14]/70">Total Questions</span>
                  <span className="font-bold text-[#2D1B14]">{userStats.total_questions}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#2D1B14]/70">Correct Answers</span>
                  <span className="font-bold text-green-600">{userStats.correct_questions}</span>
                </div>
                <div className="flex justify-between border-t border-[#2D1B14]/10 pt-3">
                  <span className="text-[#2D1B14]/70">Overall Accuracy</span>
                  <span className="font-bold text-[#2D1B14]">{Math.round(userStats.global_accuracy)}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Concept Mastery Visualization */}
        {topicList.length > 0 && (
          <div className="mb-16">
            <h2 className="text-2xl font-black font-playfair text-[#2D1B14] mb-6 flex items-center gap-3">
              <Target className="w-6 h-6 text-[#D4AF37]" /> Concept Mastery
            </h2>

            <div className="space-y-12">
              {topicList.map(topic => {
                const concepts = masteryByTopic[topic] || [];
                return (
                  <div key={topic}>
                    <h3 className="text-lg font-bold font-playfair text-[#2D1B14] mb-6">{topic}</h3>

                    <div className="space-y-4">
                      {concepts.map((concept, idx) => {
                        const theta = concept.theta;
                        const level = getThetaLabel(theta);
                        const color = getThetaColor(theta);
                        // Normalize theta to 0-100 for visualization (-3 to 3)
                        const progress = Math.round(((theta + 3) / 6) * 100);

                        return (
                          <div key={idx} className="space-y-2">
                            <div className="flex items-end justify-between">
                              <div>
                                <div className="font-bold text-[#2D1B14]">{concept.concept}</div>
                                <div className="text-xs text-[#2D1B14]/60">
                                  Θ = {theta.toFixed(2)} • {concept.responses} responses
                                </div>
                              </div>
                              <div className={`px-3 py-1 rounded text-white text-xs font-bold ${color}`}>
                                {level}
                              </div>
                            </div>

                            {/* Progress Bar */}
                            <div className="w-full h-4 bg-[#2D1B14]/10 rounded-full overflow-hidden">
                              <div
                                className={`h-full transition-all ${color}`}
                                style={{ width: `${progress}%` }}
                              />
                            </div>

                            {/* Theta Scale Reference */}
                            <div className="text-[10px] text-[#2D1B14]/50 flex justify-between px-1">
                              <span>Novice (-3)</span>
                              <span>Beginner (-1.5)</span>
                              <span>Intermediate (0)</span>
                              <span>Advanced (1.5)</span>
                              <span>Expert (3)</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {concepts.length === 0 && (
                      <div className="p-4 text-center text-[#2D1B14]/60 italic">
                        No concepts tracked yet
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Empty State */}
        {topicList.length === 0 && (
          <div className="p-12 text-center bg-[#2D1B14]/5 border border-dashed border-[#2D1B14]/20 rounded-lg">
            <BookOpen className="w-12 h-12 mx-auto text-[#2D1B14]/40 mb-4" />
            <p className="text-[#2D1B14]/60 font-semibold">No concepts tracked yet</p>
            <p className="text-sm text-[#2D1B14]/50 mt-2">Start answering questions to build your concept mastery profile</p>
          </div>
        )}
      </div>
    </InternalLayout>
  );
};

export default Profile;
