/**
 * pages/PvPRoom.tsx — PvP 1v1 matchmaking and quiz room.
 *
 * Phases:
 *   1. Topic selection + join queue
 *   2. Matchmaking (polling for opponent)
 *   3. Quiz (shared questions, competing scores)
 *   4. Results (winner, Elo change)
 */

import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import InternalLayout from '../components/InternalLayout';
import {
  joinQueue,
  leaveQueue,
  getQueueStatus,
  getMatch,
  submitPvPAnswer,
  endPvPMatch,
  getPvPRating,
  getLeaderboard,
  type PvPMatchData,
  type PvPQuestion,
  type SubmitAnswerResponse,
  type EndMatchResponse,
  type PvPRating,
  type LeaderboardEntry,
} from '../services/pvpService';

type Phase = 'lobby' | 'searching' | 'playing' | 'results';

// Render full PvP flow: queueing, live match, and result summary.
export default function PvPRoom() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // State
  const [phase, setPhase] = useState<Phase>('lobby');
  const [topic, setTopic] = useState('Mixed');
  const [error, setError] = useState('');

  // Matchmaking
  const [opponentName, setOpponentName] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Match
  const [match, setMatch] = useState<PvPMatchData | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<SubmitAnswerResponse | null>(null);
  const [myScore, setMyScore] = useState(0);
  const [oppScore, setOppScore] = useState(0);
  const startTime = useRef(Date.now());

  // Results
  const [results, setResults] = useState<EndMatchResponse | null>(null);

  // Rating & Leaderboard
  const [rating, setRating] = useState<PvPRating | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);

  // Load rating & leaderboard on mount
  useEffect(() => {
    if (user) {
      getPvPRating(user.id).then(setRating).catch(() => {});
      getLeaderboard(10).then(r => setLeaderboard(r.entries)).catch(() => {});
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [user]);

  // ── Join Queue ──────────────────────────────────────────────────────

  // Join matchmaking queue and start polling for match assignment.
  const handleJoinQueue = async () => {
    setError('');
    try {
      await joinQueue(topic);
      setPhase('searching');

      // Poll for match
      pollRef.current = setInterval(async () => {
        try {
          const status = await getQueueStatus();
          if (status.status === 'matched' && status.match_id) {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            setOpponentName(status.opponent_username || 'Opponent');
            const matchData = await getMatch(status.match_id);
            setMatch(matchData);
            setCurrentIndex(matchData.questions[0]?.index ?? 0);
            setPhase('playing');
            startTime.current = Date.now();
          }
        } catch { /* keep polling */ }
      }, 2500);
    } catch (e: any) {
      setError(e.message || 'Failed to join queue');
    }
  };

  // Cancel matchmaking and return to lobby.
  const handleLeaveQueue = async () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    await leaveQueue().catch(() => {});
    setPhase('lobby');
  };

  // ── Submit Answer ──────────────────────────────────────────────────

  // Submit one answer for the active PvP question and update scores.
  const handleAnswer = async (answer: string) => {
    if (!match || selectedAnswer) return;
    setSelectedAnswer(answer);

    const q = match.questions[0];
    if (!q) {
      setError('No playable question is available right now. Please wait for sync.');
      return;
    }
    const timeTaken = (Date.now() - startTime.current) / 1000;

    try {
      const result = await submitPvPAnswer(
        match.match_id, q.id, q.index, answer, timeTaken,
      );
      setFeedback(result);
      setMyScore(result.your_score);
      setOppScore(result.opponent_score);

      if (result.match_finished) {
        setTimeout(async () => {
          try {
            const endResult = await endPvPMatch(match.match_id);
            setResults(endResult);
            setPhase('results');
            // Refresh rating
            if (user) getPvPRating(user.id).then(setRating).catch(() => {});
          } catch { setPhase('results'); }
        }, 1500);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to submit answer');
    }
  };

  // Advance to next question or finalize match when questions are exhausted.
  const handleNextQuestion = () => {
    if (!match) return;

    if (feedback?.next_question) {
      setMatch(prev => prev ? { ...prev, questions: [feedback.next_question as PvPQuestion] } : prev);
      setCurrentIndex(feedback.next_question.index);
      setSelectedAnswer(null);
      setFeedback(null);
      startTime.current = Date.now();
      return;
    }

    // No next question means the server considers this player's sequence complete.
    endPvPMatch(match.match_id).then(r => {
      setResults(r);
      setPhase('results');
      if (user) getPvPRating(user.id).then(setRating).catch(() => {});
    }).catch(() => setPhase('results'));
  };

  const currentQ: PvPQuestion | null = match?.questions[0] ?? null;

  // ── Render (Tailwind Style Overhaul) ──────────────────────────────────

  return (
    <InternalLayout>
      <div className="max-w-4xl mx-auto p-8">
        <h1 className="text-4xl font-black font-playfair text-[#2D1B14] mb-8">
          PvP Arena
        </h1>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6 font-bold text-sm">
            {error}
          </div>
        )}

        {/* ── LOBBY ── */}
        {phase === 'lobby' && (
          <div className="space-y-8">
            {/* Rating Card */}
            {rating && (
              <div className="bg-white p-8 border border-[#2D1B14]/10 shadow-sm flex flex-col md:flex-row justify-between items-center gap-6">
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-2">Your Elo Rating</div>
                  <div className="text-4xl font-black font-playfair text-[#2D1B14]">{Math.round(rating.elo_rating)}</div>
                </div>
                <div className="flex gap-8 text-center">
                  <div>
                    <div className="text-2xl font-black font-playfair text-[#2D1B14]">{rating.total_wins}</div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/40">Wins</div>
                  </div>
                  <div>
                    <div className="text-2xl font-black font-playfair text-[#2D1B14]">{rating.total_losses}</div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/40">Losses</div>
                  </div>
                  <div>
                    <div className="text-2xl font-black font-playfair text-[#2D1B14]">{rating.total_draws}</div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/40">Draws</div>
                  </div>
                  <div>
                    <div className="text-2xl font-black font-playfair text-[#D4AF37]">{rating.win_rate}%</div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/40">Win Rate</div>
                  </div>
                </div>
              </div>
            )}

            {/* Topic Selector */}
            <div className="bg-white p-8 border border-[#2D1B14]/10 shadow-sm">
              <label className="block text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-4">Select Topic</label>
              <div className="flex gap-4 mb-8">
                {['Mixed', 'History', 'Geography'].map(t => (
                  <button
                    key={t}
                    onClick={() => setTopic(t)}
                    className={`flex-1 py-4 text-xs font-bold uppercase tracking-widest border transition-all ${
                      topic === t 
                        ? 'bg-[#2D1B14] text-[#F5F2E7] border-[#2D1B14] shadow-md' 
                        : 'bg-transparent text-[#2D1B14]/60 border-[#2D1B14]/20 hover:border-[#D4AF37]'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <button
                onClick={handleJoinQueue}
                className="w-full py-4 bg-[#D4AF37] text-white text-sm font-bold uppercase tracking-[0.2em] shadow-lg hover:bg-[#c29e2e] transition-colors flex justify-center items-center gap-2"
              >
                Find Opponent
              </button>
            </div>

            {/* Leaderboard */}
            {leaderboard.length > 0 && (
              <div className="bg-white p-8 border border-[#2D1B14]/10 shadow-sm">
                <h3 className="text-xs font-bold uppercase tracking-[0.3em] text-[#D4AF37] mb-6">Leaderboard</h3>
                <div className="space-y-4">
                  {leaderboard.map(e => (
                    <div key={e.user_id} className="flex justify-between items-center py-3 border-b border-[#2D1B14]/5 last:border-0">
                      <div className="flex items-center gap-4">
                        <span className="text-lg font-black font-playfair text-[#2D1B14]/40 w-8">#{e.rank}</span>
                        <span className="font-bold text-[#2D1B14]">{e.username}</span>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-black font-playfair text-[#D4AF37]">{Math.round(e.elo_rating)} Elo</div>
                        <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/40">{e.total_wins} Wins ({e.win_rate}%)</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── SEARCHING ── */}
        {phase === 'searching' && (
          <div className="text-center py-24 bg-white border border-[#2D1B14]/10 shadow-sm">
            <div className="w-16 h-16 mx-auto mb-8 border-4 border-[#2D1B14]/10 border-t-[#D4AF37] rounded-full animate-spin"></div>
            <h2 className="text-2xl font-black font-playfair text-[#2D1B14] mb-2">Searching for opponent...</h2>
            <p className="text-[#2D1B14]/60 mb-8 uppercase tracking-widest text-xs font-bold">Topic: {topic}</p>
            <button 
              onClick={handleLeaveQueue} 
              className="px-8 py-3 bg-transparent border border-[#2D1B14]/20 text-[#2D1B14]/60 text-xs font-bold uppercase tracking-widest hover:border-[#D4AF37] hover:text-[#D4AF37] transition-colors"
            >
              Cancel Matchmaking
            </button>
          </div>
        )}

        {/* ── PLAYING ── */}
        {phase === 'playing' && currentQ && (
          <div className="space-y-6">
            {/* Score bar */}
            <div className="flex justify-between items-center bg-white border border-[#2D1B14]/10 p-6 shadow-sm">
              <div className="text-center">
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-1">You</div>
                <div className="text-2xl font-black font-playfair text-[#2D1B14]">{myScore}</div>
              </div>
              <div className="text-center">
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/40 mb-1">Question</div>
                <div className="text-xl font-black font-playfair text-[#2D1B14]">{currentIndex + 1} <span className="text-lg text-[#2D1B14]/40">/ {match!.total_questions}</span></div>
              </div>
              <div className="text-center">
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-1">{opponentName}</div>
                <div className="text-2xl font-black font-playfair text-[#2D1B14]">{oppScore}</div>
              </div>
            </div>

            {/* Question */}
            <div className="bg-[#FDFCF7] border border-[#2D1B14]/10 p-10 shadow-sm">
              <p className="text-xl leading-relaxed text-[#2D1B14] font-medium text-center">{currentQ.text}</p>
            </div>

            {/* Options */}
            <div className="grid grid-cols-1 gap-4">
              {currentQ.options.map((opt, i) => {
                let bgClass = 'bg-white hover:border-[#D4AF37]';
                let borderClass = 'border-[#2D1B14]/10';
                let textClass = 'text-[#2D1B14]';

                if (feedback && selectedAnswer) {
                  if (opt.trim() === feedback.correct_answer.trim()) { 
                    bgClass = 'bg-green-50'; 
                    borderClass = 'border-green-500';
                    textClass = 'text-green-800 font-bold';
                  } else if (opt === selectedAnswer && !feedback.is_correct) { 
                    bgClass = 'bg-red-50'; 
                    borderClass = 'border-red-500';
                    textClass = 'text-red-800';
                  }
                }

                return (
                  <button
                    key={i}
                    onClick={() => handleAnswer(opt)}
                    disabled={!!selectedAnswer}
                    className={`p-6 text-left border shadow-sm transition-all text-lg ${bgClass} ${borderClass} ${textClass} ${selectedAnswer ? 'cursor-default' : 'cursor-pointer hover:shadow-md'}`}
                  >
                    {opt}
                  </button>
                );
              })}
            </div>

            {/* Feedback */}
            {feedback && (
              <div className="mt-8 bg-white p-8 border border-[#2D1B14]/10 shadow-sm">
                {feedback.explanation && (
                  <p className="text-[#2D1B14]/80 text-sm leading-relaxed mb-6 italic border-l-4 border-[#D4AF37] pl-4">
                    {feedback.explanation}
                  </p>
                )}
                {!feedback.match_finished && (
                  <button 
                    onClick={handleNextQuestion} 
                    className="w-full py-4 bg-[#2D1B14] text-[#F5F2E7] text-xs font-bold uppercase tracking-[0.2em] shadow-lg hover:bg-[#3d261c] transition-colors"
                  >
                    Next Question
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── RESULTS ── */}
        {phase === 'results' && (
          <div className="text-center py-16 bg-white border border-[#2D1B14]/10 shadow-sm">
            <div className="text-6xl mb-6">
              {results?.result === 'win' ? '🏆' : results?.result === 'loss' ? '😞' : '🤝'}
            </div>
            <h2 className="text-4xl font-black font-playfair text-[#2D1B14] mb-8">
              {results?.result === 'win' ? 'Victory!' : results?.result === 'loss' ? 'Defeat' : 'Draw'}
            </h2>

            <div className="flex justify-center items-center gap-12 mb-12">
              <div className="text-center">
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-2">You</div>
                <div className="text-5xl font-black font-playfair text-[#2D1B14]">{results?.your_score ?? myScore}</div>
              </div>
              <div className="text-3xl font-black font-playfair text-[#2D1B14]/20">VS</div>
              <div className="text-center">
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#D4AF37] mb-2">{results?.opponent_username || 'Opponent'}</div>
                <div className="text-5xl font-black font-playfair text-[#2D1B14]">{results?.opponent_score ?? oppScore}</div>
              </div>
            </div>

            {results && (
              <div className="mb-12 inline-block bg-[#FDFCF7] border border-[#2D1B14]/10 px-8 py-4 shadow-inner">
                <div className="text-[10px] font-bold uppercase tracking-widest text-[#2D1B14]/60 mb-2">Elo Rating Update</div>
                <div className="text-2xl font-black font-playfair text-[#2D1B14]">
                  {Math.round(results.new_elo - results.elo_change)} <span className="text-[#D4AF37]">→</span> {Math.round(results.new_elo)}
                </div>
                <div className={`text-xs font-bold mt-1 ${results.elo_change > 0 ? 'text-green-600' : results.elo_change < 0 ? 'text-red-600' : 'text-[#2D1B14]/60'}`}>
                  {results.elo_change > 0 ? '+' : ''}{results.elo_change.toFixed(1)} Points
                </div>
              </div>
            )}

            <div className="flex justify-center gap-4">
              <button
                onClick={() => {
                  setPhase('lobby');
                  setMatch(null);
                  setCurrentIndex(0);
                  setSelectedAnswer(null);
                  setFeedback(null);
                  setResults(null);
                  setMyScore(0);
                  setOppScore(0);
                  getLeaderboard(10).then(r => setLeaderboard(r.entries)).catch(() => {});
                }}
                className="px-8 py-4 bg-[#D4AF37] text-white text-xs font-bold uppercase tracking-[0.2em] shadow-lg hover:bg-[#c29e2e] transition-colors"
              >
                Play Again
              </button>
              <button
                onClick={() => navigate('/dashboard')}
                className="px-8 py-4 bg-transparent border border-[#2D1B14]/20 text-[#2D1B14]/60 text-xs font-bold uppercase tracking-[0.2em] hover:border-[#D4AF37] hover:text-[#D4AF37] transition-colors"
              >
                Return to Dashboard
              </button>
            </div>
          </div>
        )}
      </div>
    </InternalLayout>
  );
}
