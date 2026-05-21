import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import InternalLayout from '../components/InternalLayout';
import {
  ArrowLeft,
  ArrowUp,
  ArrowDown,
  ArrowRight,
  Trophy,
  Loader2,
  CheckCircle2,
  XCircle,
  Crown,
  BookMarked,
  Lock,
} from 'lucide-react';
import {
  getUserRank,
  startChallengeSession,
  submitChallengeAnswer,
  generateChallengeQuestion,
  endChallengeSession,
} from '../services/challengeService';
import {
  UserRank,
  ChallengeLevel,
  ChallengeQuestion,
  ChallengeSessionState,
  ForceLevelChange,
  Rank,
  EndSessionResponse,
  RANK_LABELS,
  LEVEL_BADGES,
} from '../types/challenge';

type Step = 'loading' | 'selection' | 'quiz' | 'summary';

const ChallengeRoom: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('loading');
  const [userRank, setUserRank] = useState<UserRank | null>(null);
  const [session, setSession] = useState<ChallengeSessionState | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedAnswer, setSelectedAnswer] = useState<string>('');
  const [isAnswered, setIsAnswered] = useState(false);
  const [forceLevelPopup, setForceLevelPopup] = useState<ForceLevelChange | null>(null);
  const [promotionModal, setPromotionModal] = useState<Rank | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [endResult, setEndResult] = useState<EndSessionResponse | null>(null);

  // Load user rank on mount
  useEffect(() => {
    const fetchRank = async () => {
      try {
        const rank = await getUserRank();
        setUserRank(rank);
        setStep('selection');
      } catch (err: any) {
        setError(err.message || 'Failed to load rank');
        setStep('selection');
      }
    };
    fetchRank();
  }, []);

  const handleStartSession = async (level: ChallengeLevel) => {
    setIsLoading(true);
    setError(null);
    try {
      const initialSession = await startChallengeSession('Mixed', level);
      setSession(initialSession);
      setStep('quiz');
    } catch (err: any) {
      setError(err.message || 'Failed to start challenge session');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAnswerSubmit = async (answer?: string) => {
    if (!session || isAnswered) return;

    const answerToSubmit = answer || selectedAnswer;
    setSelectedAnswer(answerToSubmit);
    setIsAnswered(true);

    try {
      const result = await submitChallengeAnswer(session, answerToSubmit);

      // Update session state
      setSession(prev => {
        if (!prev) return null;
        return {
          ...prev,
          score: result.is_correct ? prev.score + 1 : prev.score,
          pointsEarned: prev.pointsEarned + result.points_change,
          rank_points: prev.rank_points + result.points_change,
          streak_correct: result.streak_correct,
          streak_wrong: result.streak_wrong,
          current_level: result.new_level,
          force_level_change: result.force_level_change,
        };
      });

      if (result.force_level_change) {
        setForceLevelPopup(result.force_level_change);
        setTimeout(() => setForceLevelPopup(null), 3000);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to submit answer');
    }
  };

  const handleNextQuestion = async () => {
    if (!session) return;

    if (session.currentIndex >= 9) {
      // End session after 10 questions
      setIsLoading(true);
      try {
        const endResult = await endChallengeSession(session.session_id);
        setEndResult(endResult);
        
        // Check for promotion
        const oldRank = userRank?.current_rank.name;
        const newRankData = await getUserRank();
        if (oldRank && oldRank !== newRankData.current_rank.name) {
          setPromotionModal(newRankData.current_rank.name);
        }
        setUserRank(newRankData);
        setStep('summary');
      } catch (err: any) {
        setError(err.message || 'Failed to end session');
      } finally {
        setIsLoading(false);
      }
      return;
    }

    setIsLoading(true);
    setIsAnswered(false);
    setSelectedAnswer('');

    try {
      const nextQ = await generateChallengeQuestion(
        session.topic,
        session.current_level,
        session.session_id
      );
      setSession(prev => {
        if (!prev) return null;
        return {
          ...prev,
          currentIndex: prev.currentIndex + 1,
          questions: [...prev.questions, nextQ],
        };
      });
    } catch (err: any) {
      setError(err.message || 'Failed to load next question');
    } finally {
      setIsLoading(false);
    }
  };

  // Loading state
  if (step === 'loading' || !userRank) {
    return (
      <InternalLayout>
        <div className="flex items-center justify-center h-full">
          <Loader2 className="w-8 h-8 animate-spin text-[#D4AF37]" />
        </div>
      </InternalLayout>
    );
  }

  // Level Selection
  if (step === 'selection') {
    const rankName = userRank.current_rank.name;
    const availableLevels = userRank.available_levels;

    return (
      <InternalLayout>
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 hover:text-[#D4AF37] mb-12 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </button>

        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <div className="inline-block mb-6">
              <div className="flex items-center gap-3 px-5 py-2 border border-[#D4AF37]/40 rounded-full text-[11px] font-bold uppercase tracking-[0.4em] text-[#D4AF37]">
                <Crown className="w-3 h-3 fill-current" /> Challenge Room
              </div>
            </div>
            <h1 className="text-5xl font-black font-playfair text-[#2D1B14] mb-4">The Gauntlet</h1>
            <p className="text-xl text-[#2D1B14]/60 italic">Ascend through the ranks of the intellectual elite.</p>
          </div>

          {error && (
            <div className="mb-8 p-4 bg-red-50 border border-red-200 text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Rank Bar */}
          <div className="bg-white p-8 border border-[#2D1B14]/10 shadow-sm mb-12">
            <div className="flex justify-between items-center mb-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-[#2D1B14] text-[#D4AF37] flex items-center justify-center font-black text-2xl border-2 border-[#D4AF37] rotate-3">
                  {rankName.charAt(0)}
                </div>
                <div>
                  <div className="text-xs font-bold uppercase tracking-widest opacity-40">Current Rank</div>
                  <div className="text-xl font-black font-playfair text-[#2D1B14]">
                    {RANK_LABELS[rankName] || rankName}
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs font-bold uppercase tracking-widest opacity-40">Total Points</div>
                <div className="text-xl font-black font-playfair text-[#2D1B14]">{userRank.rank_points}</div>
              </div>
            </div>
            <div className="w-full h-2 bg-[#2D1B14]/5 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-[#D4AF37]"
                initial={{ width: 0 }}
                animate={{ width: `${(userRank.rank_points % 1000) / 10}%` }}
              />
            </div>
          </div>

          {/* Level Selection */}
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6">
            {([1, 2, 3, 4, 5] as ChallengeLevel[]).map((lvl) => {
              const isAvailable = availableLevels.includes(lvl);
              return (
                <button
                  key={lvl}
                  disabled={!isAvailable || isLoading}
                  onClick={() => handleStartSession(lvl)}
                  className={`relative group p-8 border transition-all flex flex-col items-center text-center ${
                    isAvailable
                      ? 'bg-white border-[#2D1B14]/10 hover:border-[#D4AF37] hover:shadow-xl cursor-pointer'
                      : 'bg-[#2D1B14]/5 border-transparent opacity-40 cursor-not-allowed'
                  }`}
                >
                  <div
                    className={`w-12 h-12 mb-6 flex items-center justify-center font-black text-xl border-2 ${
                      isAvailable
                        ? 'bg-[#F5F2E7] text-[#2D1B14] border-[#D4AF37]'
                        : 'bg-gray-200 text-gray-400 border-gray-300'
                    }`}
                  >
                    {LEVEL_BADGES[lvl]}
                  </div>
                  <div className="text-sm font-bold uppercase tracking-widest mb-2">Level {lvl}</div>
                  {!isAvailable && <Lock className="w-4 h-4 text-[#2D1B14]/40 mt-auto" />}
                  {isAvailable && (
                    <div className="text-[10px] font-bold text-[#D4AF37] mt-auto uppercase tracking-widest group-hover:translate-x-1 transition-transform">
                      Enter →
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </InternalLayout>
    );
  }

  // Quiz
  if (step === 'quiz' && session) {
    // Safety check: ensure currentIndex is within bounds
    if (session.currentIndex >= session.questions.length) {
      return (
        <InternalLayout>
          <div className="flex items-center justify-center h-screen">
            <h2 className="text-2xl font-bold text-[#2D1B14]">Error: Question not found</h2>
          </div>
        </InternalLayout>
      );
    }

    const currentQ = session.questions[session.currentIndex] as ChallengeQuestion;

    return (
      <InternalLayout>
        <div className="max-w-3xl mx-auto relative">
          {/* Force Level Popup */}
          <AnimatePresence>
            {forceLevelPopup && (
              <motion.div
                initial={{ opacity: 0, y: -50, scale: 0.8 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                className={`absolute -top-20 left-1/2 -translate-x-1/2 z-50 px-8 py-4 rounded-sm shadow-2xl flex items-center gap-4 border-2 ${
                  forceLevelPopup.direction === 'up'
                    ? 'bg-green-600 border-green-400 text-white'
                    : 'bg-red-600 border-red-400 text-white'
                }`}
              >
                {forceLevelPopup.direction === 'up' ? (
                  <ArrowUp className="w-6 h-6" />
                ) : (
                  <ArrowDown className="w-6 h-6" />
                )}
                <span className="font-bold uppercase tracking-widest text-sm">{forceLevelPopup.reason}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Quiz Header */}
          <div className="flex justify-between items-center mb-12 pb-6 border-b border-[#D4AF37]/20">
            <div className="flex items-center gap-6">
              <div className="w-12 h-12 bg-[#2D1B14] text-[#D4AF37] flex items-center justify-center font-black text-xl border-2 border-[#D4AF37]">
                {LEVEL_BADGES[session.current_level]}
              </div>
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#D4AF37]">
                  Question {session.currentIndex + 1} / 10
                </div>
                <div className="text-sm font-bold text-[#2D1B14]">Level {session.current_level} Challenge</div>
              </div>
            </div>

            <div className="flex items-center gap-8">
              <div className="text-center">
                <div className="text-xs font-bold uppercase tracking-widest opacity-40">Rank Points</div>
                <motion.div
                  key={session.pointsEarned}
                  initial={{ scale: 1.5, color: '#D4AF37' }}
                  animate={{ scale: 1, color: '#2D1B14' }}
                  className="text-2xl font-black font-playfair"
                >
                  {session.pointsEarned >= 0 ? '+' : ''}{session.pointsEarned}
                </motion.div>
              </div>
              <div className="text-center">
                <div className="text-xs font-bold uppercase tracking-widest opacity-40">Streak</div>
                <div className="flex gap-1 mt-1">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className={`w-2 h-2 rounded-full transition-all ${
                        i <= session.streak_correct
                          ? 'bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.6)]'
                          : 'bg-[#2D1B14]/10'
                      }`}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Question Area */}
          <div className="mb-12">
            <div className="text-[#D4AF37] text-[10px] font-bold uppercase tracking-[0.4em] mb-4">
              Worth {currentQ.points_value} Points
            </div>
            <h2 className="text-3xl font-black font-playfair text-[#2D1B14] mb-10 leading-relaxed">
              {currentQ.text}
            </h2>

            {currentQ.is_free_text ? (
              <div className="space-y-4">
                <input
                  type="text"
                  value={selectedAnswer}
                  onChange={(e) => setSelectedAnswer(e.target.value)}
                  disabled={isAnswered}
                  placeholder="Type your scholarly answer..."
                  className="w-full p-6 bg-white border border-[#2D1B14]/10 text-xl font-serif italic focus:border-[#D4AF37] outline-none transition-all"
                />
                {!isAnswered && (
                  <button
                    onClick={() => handleAnswerSubmit()}
                    className="w-full py-4 bg-[#2D1B14] text-[#F5F2E7] text-[10px] font-bold uppercase tracking-[0.3em] hover:bg-[#3d261c] transition-all"
                  >
                    Submit Answer
                  </button>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {currentQ.options.map((option, idx) => {
                  const isSelected = selectedAnswer === option;
                  const isCorrect = isAnswered && option === currentQ.correctAnswer;
                  const isWrong = isAnswered && isSelected && option !== currentQ.correctAnswer;

                  return (
                    <button
                      key={idx}
                      disabled={isAnswered}
                      onClick={() => handleAnswerSubmit(option)}
                      className={`p-6 text-left border transition-all flex items-center justify-between group ${
                        isCorrect
                          ? 'bg-green-50 border-green-500 text-green-900'
                          : isWrong
                          ? 'bg-red-50 border-red-500 text-red-900'
                          : isSelected
                          ? 'border-[#D4AF37] bg-[#FDFCF7]'
                          : 'bg-white border-[#2D1B14]/10 hover:border-[#D4AF37]/50'
                      }`}
                    >
                      <span className="font-serif italic">{option}</span>
                      {isCorrect && <CheckCircle2 className="w-5 h-5 text-green-600" />}
                      {isWrong && <XCircle className="w-5 h-5 text-red-600" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Explanation */}
          <AnimatePresence>
            {isAnswered && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-8 bg-white border border-[#2D1B14]/10 shadow-lg"
              >
                <div className="flex items-center gap-3 mb-4">
                  <BookMarked className="w-5 h-5 text-[#D4AF37]" />
                  <span className="text-xs font-bold uppercase tracking-widest text-[#D4AF37]">
                    Scholarly Context
                  </span>
                </div>
                <p className="text-lg font-serif italic text-[#2D1B14]/80 leading-relaxed mb-8">
                  {currentQ.explanation}
                </p>
                <button
                  onClick={handleNextQuestion}
                  disabled={isLoading}
                  className="w-full py-4 bg-[#2D1B14] text-[#F5F2E7] text-[10px] font-bold uppercase tracking-[0.3em] hover:bg-[#3d261c] transition-all flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      Continue Ascent <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </InternalLayout>
    );
  }

  // Summary
  if (step === 'summary' && session) {
    return (
      <InternalLayout>
        <div className="max-w-2xl mx-auto text-center">
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="w-24 h-24 bg-[#2D1B14] rounded-full flex items-center justify-center border-4 border-[#D4AF37] shadow-2xl mx-auto mb-8"
          >
            <Trophy className="text-[#D4AF37] w-10 h-10" />
          </motion.div>

          <h1 className="text-5xl font-black font-playfair text-[#2D1B14] mb-4">Gauntlet Concluded</h1>
          <p className="text-xl text-[#2D1B14]/60 italic mb-12">
            Your performance has shifted the balance of the archives.
          </p>

          <div className="grid grid-cols-2 gap-8 mb-16">
            <div className="p-8 bg-white border border-[#2D1B14]/10">
              <div className="text-4xl font-black font-playfair text-[#2D1B14] mb-1">
                {session.pointsEarned >= 0 ? '+' : ''}{session.pointsEarned}
              </div>
              <div className="text-[10px] font-bold uppercase tracking-widest opacity-40">Rank Points Gained</div>
            </div>
            <div className="p-8 bg-white border border-[#2D1B14]/10">
              <div className="text-4xl font-black font-playfair text-[#2D1B14] mb-1">
                {session.score}/10
              </div>
              <div className="text-[10px] font-bold uppercase tracking-widest opacity-40">Correct Answers</div>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={() => navigate('/dashboard')}
              className="px-10 py-5 border border-[#2D1B14] text-[10px] font-bold uppercase tracking-[0.3em] hover:bg-[#2D1B14] hover:text-[#F5F2E7] transition-all"
            >
              Return to Dashboard
            </button>
            <button
              onClick={() => {
                setStep('selection');
                setSession(null);
                setEndResult(null);
                getUserRank()
                  .then(setUserRank)
                  .catch((err: any) => {
                    setError(err.message || 'Failed to load rank');
                    console.error('Failed to fetch user rank:', err);
                  });
              }}
              className="px-10 py-5 bg-[#2D1B14] text-[#F5F2E7] text-[10px] font-bold uppercase tracking-[0.3em] hover:bg-[#3d261c] transition-all"
            >
              Enter Gauntlet Again
            </button>
          </div>
        </div>

        {/* Promotion Modal */}
        <AnimatePresence>
          {promotionModal && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[100] bg-[#2D1B14]/90 flex items-center justify-center p-6 backdrop-blur-sm"
            >
              <motion.div
                initial={{ scale: 0.8, y: 50 }}
                animate={{ scale: 1, y: 0 }}
                className="bg-[#F5F2E7] p-12 max-w-lg w-full text-center border-4 border-[#D4AF37] relative"
              >
                <div className="absolute -top-12 left-1/2 -translate-x-1/2 w-24 h-24 bg-[#D4AF37] rounded-full flex items-center justify-center shadow-2xl">
                  <Crown className="text-[#2D1B14] w-12 h-12" />
                </div>
                <h2 className="text-4xl font-black font-playfair text-[#2D1B14] mt-8 mb-4">PROMOTED!</h2>
                <p className="text-xl text-[#2D1B14]/60 italic mb-8">
                  You have ascended to {RANK_LABELS[promotionModal] || promotionModal}
                </p>
                <div className="text-6xl font-black text-[#2D1B14] mb-12">{promotionModal}</div>
                <button
                  onClick={() => setPromotionModal(null)}
                  className="w-full py-4 bg-[#2D1B14] text-[#F5F2E7] text-[10px] font-bold uppercase tracking-[0.3em] hover:bg-[#3d261c] transition-all"
                >
                  Accept Honor
                </button>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </InternalLayout>
    );
  }

  return null;
};

export default ChallengeRoom;
