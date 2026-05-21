/**
 * src/services/challengeService.ts
 *
 * API calls for the Challenge Room ONLY.
 * The existing apiService.ts (ClassicRoom) is NOT modified.
 *
 * Imported in ChallengeRoom.tsx:
 *   import {
 *     getUserRank, startChallengeSession,
 *     generateChallengeQuestion, submitChallengeAnswer, endChallengeSession
 *   } from '../services/challengeService';
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
import { API_BASE } from '../config';
import { authHeaders } from './http';
import { notifyDashboardStatsUpdated } from './dashboardEvents';

// ── Config ───────────────────────────────────────────────────────────────

// ── Auth helpers (re-use same localStorage UUID pattern as ClassicRoom) ───

/**
 * Get the logged-in user's ID from localStorage.
 * This is the same key ClassicRoom uses — one user, two rooms, same ID.
 */
const getUserId = (): string => {
  let id = localStorage.getItem('adaptiq_user_id');
  if (!id) {
    const legacyId = localStorage.getItem('user_id');
    if (legacyId) {
      id = legacyId;
      localStorage.setItem('adaptiq_user_id', legacyId);
    }
  }
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem('adaptiq_user_id', id);
  }
  return id;
};

/**
 * Get a JWT token if you add auth later.
 * For now, sends user_id in the request body (same as ClassicRoom).
 */
// const getAuthHeader = (): Record<string, string> => {
//   const token = localStorage.getItem('adaptiq_token');
//   return token ? { Authorization: `Bearer ${token}` } : {};
// };

const jsonHeaders = () => authHeaders();

// ── Error helper ─────────────────────────────────────────────────────────

// Parse successful JSON responses or throw backend detail errors.
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}


// ═════════════════════════════════════════════════════════════════════════
// GET /api/challenge/user/{user_id}/rank
// ═════════════════════════════════════════════════════════════════════════

/**
 * Fetch the user's current rank, points, and available starting levels.
 * Called on the selection screen to show rank badge and lock/unlock cards.
 */
// Load challenge rank snapshot for the current authenticated user.
export async function getUserRank(): Promise<UserRank> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/api/challenge/user/${userId}/rank`, {
    headers: jsonHeaders(),
  });
  const data = await handleResponse<{
    current_rank    : string;
    rank_points     : number;
    available_levels: number[];
    total_sessions  : number;
    total_questions : number;
  }>(res);

  // Map backend shape → frontend UserRank (add convenience aliases)
  return {
    current_rank    : data.current_rank     as UserRank['current_rank'],
    rank_points     : data.rank_points,
    available_levels: data.available_levels as ChallengeLevel[],
    total_sessions  : data.total_sessions,
    total_questions : data.total_questions,
    // convenience aliases used in ChallengeRoom.tsx JSX
    level_access    : data.available_levels as ChallengeLevel[],
    total_points    : data.rank_points,
  };
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/challenge/start-session  →  ChallengeSessionState
// ═════════════════════════════════════════════════════════════════════════

/**
 * Create a new challenge session and load the first question.
 * Returns the full initial ChallengeSessionState used by React useState.
 */
// Start a new challenge session and hydrate initial client state.
export async function startChallengeSession(
  topic        : TopicType,
  startingLevel: ChallengeLevel,
): Promise<ChallengeSessionState> {
  const userId = getUserId();

  // 1. Create session
  const sessionRes = await fetch(`${API_BASE}/api/challenge/start-session`, {
    method : 'POST',
    headers: jsonHeaders(),
    body   : JSON.stringify({
      user_id       : userId,
      topic,
      starting_level: startingLevel,
    }),
  });
  const sessionData = await handleResponse<StartSessionResponse>(sessionRes);

  // 2. Load first question immediately
  const firstQuestion = await generateChallengeQuestion(
    topic,
    sessionData.current_level as ChallengeLevel,
    sessionData.session_id,
  );

  // 2b. Prefetch two follow-up questions in background to reduce lag during play
  (async () => {
    try {
      const q1 = await generateChallengeQuestion(topic, sessionData.current_level as ChallengeLevel, sessionData.session_id);
      const q2 = await generateChallengeQuestion(topic, sessionData.current_level as ChallengeLevel, sessionData.session_id);
      // Try to store them in a lightweight client-side cache (localStorage) for session use
      try {
        const key = `challenge_prefetch_${sessionData.session_id}`;
        const existing = JSON.parse(localStorage.getItem(key) || '[]');
        localStorage.setItem(key, JSON.stringify([...existing, q1, q2]));
      } catch (e) {
        // ignore storage failures
      }
    } catch (e) {
      // Ignore prefetch failures — generation will occur on demand
      console.debug('Challenge prefetch failed', e);
    }
  })();

  // 3. Build initial session state
  return {
    session_id    : sessionData.session_id,
    topic,
    current_level : sessionData.current_level as ChallengeLevel,
    current_rank  : sessionData.current_rank,
    rank_points   : 0,
    streak_correct: 0,
    streak_wrong  : 0,
    questions     : [firstQuestion],
    currentIndex  : 0,
    score         : 0,
    pointsEarned  : 0,
    force_level_change: null,
  };
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/challenge/generate-question
// ═════════════════════════════════════════════════════════════════════════

/**
 * Generate the next challenge question at the current level.
 * Called after each correct answer or forced level change.
 */
// Request one challenge question for the active session and level.
export async function generateChallengeQuestion(
  topic    : TopicType,
  level    : ChallengeLevel,
  sessionId: string,
): Promise<ChallengeQuestion> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/api/challenge/generate-question`, {
    method : 'POST',
    headers: jsonHeaders(),
    body   : JSON.stringify({
      session_id: sessionId,
      user_id   : userId,
      topic,
      level,
    }),
  });
  return handleResponse<ChallengeQuestion>(res);
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/challenge/submit-answer
// ═════════════════════════════════════════════════════════════════════════

/**
 * Submit the user's answer for the current question.
 * Returns whether it's correct, points change, new level, and streak state.
 * If force_level_change is present, the frontend should show the popup.
 */
// Submit one challenge answer and return scoring/progression updates.
export async function submitChallengeAnswer(
  session       : ChallengeSessionState,
  selectedAnswer: string,
): Promise<SubmitAnswerResponse> {
  const userId = getUserId();
  const currentQuestion = session.questions[session.currentIndex];

  const res = await fetch(`${API_BASE}/api/challenge/submit-answer`, {
    method : 'POST',
    headers: jsonHeaders(),
    body   : JSON.stringify({
      session_id : session.session_id,
      question_id: currentQuestion.id,
      user_id    : userId,
      answer     : selectedAnswer,
      time_taken : null,   // optional — add timer value here if you have one
    }),
  });
  const data = await handleResponse<SubmitAnswerResponse>(res);
  notifyDashboardStatsUpdated();
  return data;
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/challenge/session/{session_id}/end
// ═════════════════════════════════════════════════════════════════════════

/**
 * End the session after 10 questions.
 * Updates global rank and returns the summary data.
 */
// Finalize challenge session and fetch rank-impact summary.
export async function endChallengeSession(
  sessionId: string,
): Promise<EndSessionResponse> {
  const res = await fetch(`${API_BASE}/api/challenge/session/${sessionId}/end`, {
    method : 'POST',
    headers: jsonHeaders(),
  });
  return handleResponse<EndSessionResponse>(res);
}


// ═════════════════════════════════════════════════════════════════════════
// (Optional) GET /api/challenge/session/{session_id}
// ═════════════════════════════════════════════════════════════════════════

/**
 * Fetch raw session state from the backend (useful for reconnect/reload).
 * Not currently used by ChallengeRoom.tsx — state is held in React.
 */
// Read raw challenge session state by id (optional reconnect helper).
export async function getChallengeSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/challenge/session/${sessionId}`, {
    headers: jsonHeaders(),
  });
  return handleResponse(res);
}
