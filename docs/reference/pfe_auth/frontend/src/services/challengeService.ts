/**
 * src/services/challengeService.ts
 *
 * API calls for the Challenge Room V2.
 * Adapted from MHD version with Main backend endpoints and JWT auth.
 */

import {
  UserRank,
  ChallengeLevel,
  ChallengeQuestion,
  ChallengeSessionState,
  StartSessionResponse,
  SubmitAnswerResponse,
  EndSessionResponse,
  TopicType,
} from '../types/challenge';
import { normalizeTopicForApi } from '../types';
import { API_BASE } from '../config';

// ── Auth helpers ─────────────────────────────────────────────────────────

const getToken = (): string | null => localStorage.getItem('adaptiq_token');

const authHeaders = (): Record<string, string> => {
  const token = getToken();
  return token
    ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
    : { 'Content-Type': 'application/json' };
};

// ── Error helper ─────────────────────────────────────────────────────────

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}


// ═════════════════════════════════════════════════════════════════════════
// GET /api/rooms/challenge/v2/status
// ═════════════════════════════════════════════════════════════════════════

/**
 * Fetch the user's current rank, points, and available starting levels.
 */
export async function getUserRank(): Promise<UserRank> {
  const res = await fetch(`${API_BASE}/api/rooms/challenge/v2/status`, {
    headers: authHeaders(),
  });
  return handleResponse<UserRank>(res);
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/rooms/challenge/v2/start
// ═════════════════════════════════════════════════════════════════════════

/**
 * Create a new challenge session and load the first question.
 */
export async function startChallengeSession(
  topic: TopicType,
  startingLevel: ChallengeLevel,
): Promise<ChallengeSessionState> {
  const res = await fetch(`${API_BASE}/api/rooms/challenge/v2/start`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      topic: normalizeTopicForApi(topic),  // FIX 2.1: Normalize topic to lowercase
      starting_level: startingLevel,
    }),
  });
  const data = await handleResponse<StartSessionResponse>(res);

  // Build initial session state
  return {
    session_id: data.session_id,
    match_id: data.match_id,
    topic,
    current_level: data.current_level,
    current_rank: data.current_rank.name,
    rank_points: 0,
    streak_correct: 0,
    streak_wrong: 0,
    questions: [data.first_question],
    currentIndex: 0,
    score: 0,
    pointsEarned: 0,
    force_level_change: null,
    available_levels: data.available_levels,
  };
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/rooms/challenge/v2/generate-question
// ═════════════════════════════════════════════════════════════════════════

/**
 * Generate the next challenge question at the current level.
 */
export async function generateChallengeQuestion(
  topic: TopicType,
  level: ChallengeLevel,
  sessionId: string,
): Promise<ChallengeQuestion> {
  const res = await fetch(`${API_BASE}/api/rooms/challenge/v2/generate-question`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      session_id: sessionId,
      topic: normalizeTopicForApi(topic),  // FIX 2.1: Normalize topic to lowercase
      level,
    }),
  });
  return handleResponse<ChallengeQuestion>(res);
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/rooms/challenge/v2/submit-answer
// ═════════════════════════════════════════════════════════════════════════

/**
 * Submit the user's answer for the current question.
 */
export async function submitChallengeAnswer(
  session: ChallengeSessionState,
  selectedAnswer: string,
  timeTaken?: number,
): Promise<SubmitAnswerResponse> {
  const currentQuestion = session.questions[session.currentIndex];

  const res = await fetch(`${API_BASE}/api/rooms/challenge/v2/submit-answer`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      session_id: session.session_id,
      question_id: currentQuestion.id,
      answer: selectedAnswer,
      time_taken: timeTaken ?? null,
    }),
  });
  return handleResponse<SubmitAnswerResponse>(res);
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/rooms/challenge/v2/session/{session_id}/end
// ═════════════════════════════════════════════════════════════════════════

/**
 * End the session after 10 questions.
 */
export async function endChallengeSession(
  sessionId: string,
): Promise<EndSessionResponse> {
  const res = await fetch(`${API_BASE}/api/rooms/challenge/v2/session/${sessionId}/end`, {
    method: 'POST',
    headers: authHeaders(),
  });
  return handleResponse<EndSessionResponse>(res);
}


// ═════════════════════════════════════════════════════════════════════════
// GET /api/rooms/challenge/v2/session/{session_id}
// ═════════════════════════════════════════════════════════════════════════

/**
 * Fetch raw session state from the backend (useful for reconnect/reload).
 */
export async function getChallengeSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/rooms/challenge/v2/session/${sessionId}`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}
