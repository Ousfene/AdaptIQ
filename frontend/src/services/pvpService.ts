/**
 * services/pvpService.ts — API calls for PvP Room.
 *
 * Covers:
 *   - joinQueue / leaveQueue / getQueueStatus (matchmaking)
 *   - getMatch / submitAnswer / endMatch (gameplay)
 *   - getRating / getLeaderboard (stats)
 */

import { API_BASE } from '../config';
import { authHeaders } from './http';
import { notifyDashboardStatsUpdated } from './dashboardEvents';

// ── Types ─────────────────────────────────────────────────────────────────

export interface JoinQueueResponse {
  queue_id: string;
  status: string;
  message: string;
}

export interface QueueStatusResponse {
  status: 'waiting' | 'matched' | 'not_in_queue' | 'expired';
  match_id: string | null;
  opponent_username: string | null;
  topic: string | null;
  message: string;
}

export interface PvPQuestion {
  id: string;
  text: string;
  options: string[];
  index: number;
}

export interface PvPMatchData {
  match_id: string;
  user1_id: string;
  user2_id: string;
  topic: string;
  status: string;
  total_questions: number;
  questions: PvPQuestion[];
  user1_score: number;
  user2_score: number;
  user1_finished: boolean;
  user2_finished: boolean;
}

export interface SubmitAnswerResponse {
  is_correct: boolean;
  correct_answer: string;
  explanation: string;
  your_score: number;
  opponent_score: number;
  questions_answered: number;
  match_finished: boolean;
  next_question?: PvPQuestion | null;
}

export interface EndMatchResponse {
  match_id: string;
  winner_id: string | null;
  result: 'win' | 'loss' | 'draw';
  your_score: number;
  opponent_score: number;
  elo_change: number;
  new_elo: number;
  opponent_username: string;
}

export interface PvPRating {
  user_id: string;
  elo_rating: number;
  total_matches: number;
  total_wins: number;
  total_losses: number;
  total_draws: number;
  win_streak: number;
  best_streak: number;
  win_rate: number;
}

export interface LeaderboardEntry {
  rank: number;
  user_id: string;
  username: string;
  elo_rating: number;
  total_wins: number;
  total_matches: number;
  win_rate: number;
}

// ── Helper ────────────────────────────────────────────────────────────────

// Resolve current user id from preferred and legacy storage keys.
const getUserId = (): string => {
  const primaryId = localStorage.getItem('adaptiq_user_id');
  if (primaryId) {
    return primaryId;
  }

  const legacyId = localStorage.getItem('user_id');
  if (legacyId) {
    localStorage.setItem('adaptiq_user_id', legacyId);
    return legacyId;
  }

  return '';
};

// Execute PvP API request and normalize backend error messages.
async function pvpFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Matchmaking ──────────────────────────────────────────────────────────

// Join matchmaking queue for selected topic.
export const joinQueue = (topic: string): Promise<JoinQueueResponse> =>
  pvpFetch('/api/pvp/join-queue', {
    method: 'POST',
    body: JSON.stringify({ user_id: getUserId(), topic }),
  });

// Leave active matchmaking queue.
export const leaveQueue = (): Promise<{ success: boolean }> =>
  pvpFetch('/api/pvp/leave-queue', {
    method: 'DELETE',
    body: JSON.stringify({ user_id: getUserId() }),
  });

// Poll current matchmaking status for active user.
export const getQueueStatus = (): Promise<QueueStatusResponse> =>
  pvpFetch(`/api/pvp/queue-status?user_id=${getUserId()}`);

// ── Match ────────────────────────────────────────────────────────────────

// Fetch match payload with only the current playable question by id.
export const getMatch = (matchId: string): Promise<PvPMatchData> =>
  pvpFetch(`/api/pvp/match/${matchId}`);

// Submit one PvP answer for current user.
export const submitPvPAnswer = (
  matchId: string,
  questionId: string,
  questionIndex: number,
  answer: string,
  timeTaken?: number,
): Promise<SubmitAnswerResponse> =>
  pvpFetch<SubmitAnswerResponse>(`/api/pvp/match/${matchId}/answer`, {
    method: 'POST',
    body: JSON.stringify({
      user_id: getUserId(),
      question_id: questionId,
      question_index: questionIndex,
      answer,
      time_taken: timeTaken,
    }),
  }).then((data) => {
    notifyDashboardStatsUpdated();
    return data;
  });

// Finalize match and return result plus Elo delta.
export const endPvPMatch = (matchId: string): Promise<EndMatchResponse> =>
  pvpFetch(`/api/pvp/match/${matchId}/end`, { method: 'POST' });

// ── Rating / Leaderboard ─────────────────────────────────────────────────

// Fetch rating profile for provided or current user.
export const getPvPRating = (userId?: string): Promise<PvPRating> =>
  pvpFetch(`/api/pvp/user/${userId || getUserId()}/rating`);

// Fetch ranked leaderboard entries.
export const getLeaderboard = (limit = 20): Promise<{ entries: LeaderboardEntry[]; total_players: number }> =>
  pvpFetch(`/api/pvp/leaderboard?limit=${limit}`);
