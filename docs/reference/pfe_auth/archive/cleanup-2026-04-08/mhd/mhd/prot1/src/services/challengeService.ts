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

// ── Config ───────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ── Auth helpers (re-use same localStorage UUID pattern as ClassicRoom) ───

/**
 * Get the logged-in user's ID from localStorage.
 * This is the same key ClassicRoom uses — one user, two rooms, same ID.
 */
const getUserId = (): string => {
  let id = localStorage.getItem('adaptiq_user_id');
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

const JSON_HEADERS = { 'Content-Type': 'application/json' };

// ── Error helper ─────────────────────────────────────────────────────────

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
export async function getUserRank(): Promise<UserRank> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/api/challenge/user/${userId}/rank`, {
    headers: JSON_HEADERS,
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
export async function startChallengeSession(
  topic        : TopicType,
  startingLevel: ChallengeLevel,
): Promise<ChallengeSessionState> {
  const userId = getUserId();

  // 1. Create session
  const sessionRes = await fetch(`${API_BASE}/api/challenge/start-session`, {
    method : 'POST',
    headers: JSON_HEADERS,
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
export async function generateChallengeQuestion(
  topic    : TopicType,
  level    : ChallengeLevel,
  sessionId: string,
): Promise<ChallengeQuestion> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/api/challenge/generate-question`, {
    method : 'POST',
    headers: JSON_HEADERS,
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
export async function submitChallengeAnswer(
  session       : ChallengeSessionState,
  selectedAnswer: string,
): Promise<SubmitAnswerResponse> {
  const userId = getUserId();
  const currentQuestion = session.questions[session.currentIndex];

  const res = await fetch(`${API_BASE}/api/challenge/submit-answer`, {
    method : 'POST',
    headers: JSON_HEADERS,
    body   : JSON.stringify({
      session_id : session.session_id,
      question_id: currentQuestion.id,
      user_id    : userId,
      answer     : selectedAnswer,
      time_taken : null,   // optional — add timer value here if you have one
    }),
  });
  return handleResponse<SubmitAnswerResponse>(res);
}


// ═════════════════════════════════════════════════════════════════════════
// POST /api/challenge/session/{session_id}/end
// ═════════════════════════════════════════════════════════════════════════

/**
 * End the session after 10 questions.
 * Updates global rank and returns the summary data.
 */
export async function endChallengeSession(
  sessionId: string,
): Promise<EndSessionResponse> {
  const res = await fetch(`${API_BASE}/api/challenge/session/${sessionId}/end`, {
    method : 'POST',
    headers: JSON_HEADERS,
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
export async function getChallengeSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/challenge/session/${sessionId}`, {
    headers: JSON_HEADERS,
  });
  return handleResponse(res);
}
