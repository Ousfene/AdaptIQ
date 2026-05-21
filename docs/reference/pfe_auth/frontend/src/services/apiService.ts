/**
 * services/apiService.ts
 * Fixed: getUserId() now reads the real authenticated user ID written by AuthContext on login/signup.
 */

import { DailyTrend, Question, RedisOpsStats, TopicBreakdown, TopicType, ConceptBreakdown, ChallengeStatus, ChallengeMatch, ChallengeAnswerResult, ChallengeResult, UserStats, ChallengeRank, ChallengeStatusV2, ChallengeMatchV2, ChallengeAnswerResultV2, ChallengeResultV2, ChallengeStartRequestV2, ChallengeQuestionMHD, ChallengeSubmitAnswerRequest, ChallengeSubmitAnswerResponse, ChallengeSessionState, ChallengeEndSessionResponse, normalizeTopicForApi } from '../types';
import { logApiErrorWithContext } from './errorTracking';
import { API_BASE } from '../config';

// ── Auth token helpers ─────────────────────────────────────────────────────
const getToken = (): string | null => localStorage.getItem('adaptiq_token');

const authHeaders = (): Record<string, string> => {
  const token = getToken();
  return token
    ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
    : { 'Content-Type': 'application/json' };
};

const safeReadJson = async (response: Response): Promise<any> => {
  try {
    if (typeof (response as any)?.json === 'function') {
      return await response.json();
    }
  } catch {
    // Ignore parse failures and return empty object fallback.
  }
  return {};
};

const safeHeaderGet = (response: Response, name: string): string | null => {
  const headers = (response as any)?.headers;
  if (headers && typeof headers.get === 'function') {
    return headers.get(name);
  }
  return null;
};

// ── Session tracking ───────────────────────────────────────────────────────
const getSessionId = (): string => {
  let id = sessionStorage.getItem('adaptiq_session_id');
  if (!id) { id = crypto.randomUUID(); sessionStorage.setItem('adaptiq_session_id', id); }
  return id;
};

// IMPORTANT: AuthContext stores the real user ID from the backend on login/signup.
// Fallback random UUID only used if somehow called before login (should not happen with ProtectedRoute).
const getUserId = (): string => {
  const id = localStorage.getItem('adaptiq_user_id');
  if (id) return id;
  const fallback = crypto.randomUUID();
  localStorage.setItem('adaptiq_user_id', fallback);
  return fallback;
};

export const resetSession = (): string => {
  const newId = crypto.randomUUID();
  sessionStorage.setItem('adaptiq_session_id', newId);
  return newId;
};

// ── Error handling helper ──────────────────────────────────────────────────
// Log detailed backend errors server-side, show generic messages to users
const handleApiError = (response: Response, err: any, endpoint?: string): Error => {
  const errorMessage = err?.detail || err?.message || 'Unknown error';
  const requestId = safeHeaderGet(response, 'X-Request-ID') || 'unknown';
  const backendMessage = typeof errorMessage === 'string' ? errorMessage.trim() : '';

  // Determine error type
  let errorType = 'APIError';
  if (response.status === 401) {
    errorType = 'AuthenticationError';
  } else if (response.status === 403) {
    errorType = 'AuthorizationError';
  } else if (response.status === 404) {
    errorType = 'NotFoundError';
  } else if (response.status === 429) {
    errorType = 'RateLimitError';
  } else if (response.status === 422) {
    errorType = 'ValidationError';
  } else if (response.status >= 500) {
    errorType = 'ServerError';
  } else if (response.status >= 400) {
    errorType = 'ClientError';
  }

  // Log to error tracker
  if (endpoint) {
    logApiErrorWithContext(errorMessage, endpoint, {
      status: response.status,
      requestId,
      errorType,
    });
  }

  // Prefer explicit backend detail when available.
  if (backendMessage && backendMessage !== 'Unknown error') {
    return new Error(backendMessage);
  }

  // Return generic error message to user
  if (response.status === 401) {
    return new Error("Authentication failed. Please log in again.");
  } else if (response.status === 403) {
    return new Error("Access denied.");
  } else if (response.status === 404) {
    return new Error("Not found.");
  } else if (response.status === 422) {
    return new Error("Invalid request. Please check your input.");
  } else if (response.status === 429) {
    return new Error("Too many requests. Please wait before trying again.");
  } else if (response.status >= 500) {
    return new Error("Server error. Please try again later.");
  } else if (response.status >= 400) {
    return new Error("Request failed. Please try again.");
  }
  return new Error("An error occurred. Please try again.");
};

// ── POST /api/rooms/classic/questions ─────────────────────────────────
export const generateQuestion = async (
  topic: TopicType,
  difficulty: number,
): Promise<Question> => {
  const endpoint = `/api/rooms/classic/questions`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      topic: normalizeTopicForApi(topic),  // FIX: Convert to lowercase for backend
      difficulty: Math.max(1, Math.min(5, Math.round(difficulty))),
      user_id: getUserId(),
      session_id: getSessionId(),
    }),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  // Type guard: validate response structure
  if (typeof data !== 'object' || data === null) {
    throw new Error('Invalid response format from API');
  }

  // Validate all required fields exist and have correct types
  const errors: string[] = [];
  if (!data.id || typeof data.id !== 'string') errors.push('missing/invalid id');
  if (!data.text || typeof data.text !== 'string') errors.push('missing/invalid text');
  if (!Array.isArray(data.options)) errors.push('missing/invalid options array');
  // NOTE: correctAnswer is now returned by submitAnswer, not generateQuestion (security fix)

  if (errors.length > 0) {
    throw new Error(`Invalid question format: ${errors.join(', ')}`);
  }

  return data as Question;
};

// ── POST /api/rooms/classic/hints ─────────────────────────────────────
export const generateHint = async (
  questionText: string,
): Promise<string> => {
  const endpoint = `/api/rooms/classic/hints`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ 
      session_id: getSessionId(),
      questionText,
    }),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  // Type guard: validate response structure
  if (typeof data !== 'object' || data === null) {
    throw new Error('Invalid response format from hint API');
  }

  if (typeof data.hint !== 'string' || data.hint.trim().length === 0) {
    throw new Error('Invalid response: missing or invalid hint text');
  }

  return data.hint as string;
};

// ── POST /api/rooms/classic/answers ───────────────────────────────────
export interface SubmitAnswerParams {
  question_id: string;
  selected_answer: string;
  time_taken: number;
  used_hint: boolean;
}

export interface SubmitAnswerResult {
  success: boolean;
  updated_difficulty: number;
  correct: boolean;  // NEW: Was the answer correct?
  correct_answer: string;  // NEW: The correct answer (revealed after submission)
}

export const submitAnswer = async (
  params: SubmitAnswerParams,
): Promise<SubmitAnswerResult> => {
  const endpoint = `/api/rooms/classic/answers`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      user_id: getUserId(),
      session_id: getSessionId(),
      question_id: params.question_id,
      selected_answer: params.selected_answer,
      time_taken: params.time_taken,
      used_hint: params.used_hint,
    }),
  });

  if (!response.ok) {
    // Keep gameplay resilient: return a safe fallback so UI can continue.
    return {
      success: false,
      updated_difficulty: 2,
      correct: false,
      correct_answer: '',
    };
  }

  const data = await response.json();

  // Type guard: validate response structure
  if (typeof data !== 'object' || data === null) {
    throw new Error('Invalid response format from submitAnswer API');
  }

  // Validate required fields
  if (typeof data.success !== 'boolean') {
    throw new Error('Invalid response: missing or invalid success field');
  }

  if (typeof data.updated_difficulty !== 'number' || data.updated_difficulty < 1 || data.updated_difficulty > 5) {
    throw new Error('Invalid response: missing or invalid updated_difficulty');
  }

  if (typeof data.correct !== 'boolean') {
    throw new Error('Invalid response: missing or invalid correct field');
  }

  if (typeof data.correct_answer !== 'string') {
    throw new Error('Invalid response: missing or invalid correct_answer field');
  }

  return data as SubmitAnswerResult;
};

// ── Configuration ───────────────────────────────────────────────────────────
const HEALTH_CHECK_TIMEOUT = 3000; // ms (configurable)

// ── Health check ──────────────────────────────────────────────────────────
export const checkApiHealth = async (): Promise<boolean> => {
  try {
    const res = await fetch(`${API_BASE}/api/system/health`, { signal: AbortSignal.timeout(HEALTH_CHECK_TIMEOUT) });
    return res.ok;
  } catch { return false; }
};

// ── GET /api/auth/stats ─────────────────────────────────────────────────
// NOTE: UserStats type is imported from types.ts to avoid duplication

export const fetchUserStats = async (): Promise<UserStats> => {
  const response = await fetch(`${API_BASE}/api/auth/stats`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err);
  }
  const data = await response.json();

  // Validate required fields exist
  const requiredFields = ['id', 'points', 'level', 'total_questions', 'correct_questions', 'global_accuracy'];
  for (const field of requiredFields) {
    if (!(field in data)) {
      throw new Error(`Invalid stats response: missing ${field}`);
    }
  }

  return data as UserStats;
};

export const fetchUserTopicBreakdown = async (): Promise<TopicBreakdown> => {
  const response = await fetch(`${API_BASE}/api/auth/stats/topic-breakdown`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err);
  }
  return await response.json() as TopicBreakdown;
};

export const fetchUserDailyTrend = async (days = 7): Promise<DailyTrend> => {
  const safeDays = Math.max(1, Math.min(90, Math.round(days)));
  const response = await fetch(`${API_BASE}/api/auth/stats/daily-trend?days=${safeDays}`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err);
  }
  return await response.json() as DailyTrend;
};

export const fetchRedisOpsStats = async (): Promise<RedisOpsStats> => {
  const response = await fetch(`${API_BASE}/api/auth/stats/redis-ops`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err);
  }
  return await response.json() as RedisOpsStats;
};

export const fetchConceptMastery = async (): Promise<ConceptBreakdown> => {
  const response = await fetch(`${API_BASE}/api/auth/stats/concept-mastery`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err);
  }
  return await response.json() as ConceptBreakdown;
};

// ── V2 ENDPOINTS (Secure, index-based answers) ─────────────────────────────────

/**
 * Normalize frontend topic to backend V2 format.
 * Frontend: "Geography", "History", "Mixed"
 * Backend V2: "geography", "history", "mix"
 */
const normalizeTopicToV2 = (topic: TopicType): string => {
  const map: Record<TopicType, string> = {
    'Geography': 'geography',
    'History': 'history',
    'Mixed': 'mix',
  };
  return map[topic];
};

export interface V2QuestionOut {
  id: string;
  text: string;
  options: string[];
  topic: string;
  difficulty: number;
  // NOTE: NO correctAnswer field (security fix)
}

export interface SessionStatsOut {
  questions_answered: number;
  correct_count: number;
}

export interface V2StartResponse {
  session_id: string;
  first_question: V2QuestionOut | null;
  session_stats: SessionStatsOut;
}

/**
 * POST /api/rooms/classic/start — Start a V2 session (secure)
 * Returns first question WITHOUT correctAnswer
 */
export const startQuizV2 = async (topic: TopicType): Promise<V2StartResponse> => {
  const endpoint = `/api/rooms/classic/start`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      topic: normalizeTopicToV2(topic),
    }),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  // Validate response structure
  if (typeof data !== 'object' || data === null) {
    throw new Error('Invalid response format from V2 start API');
  }

  if (typeof data.session_id !== 'string' || !data.session_id) {
    throw new Error('Invalid response: missing or invalid session_id');
  }

  if (typeof data.session_stats !== 'object') {
    throw new Error('Invalid response: missing session_stats');
  }

  return data as V2StartResponse;
};

export interface V2AnswerRequest {
  question_id: string;
  selected_index: number; // Index into options array (not string)
  time_taken_seconds: number;
  used_hint: boolean;
}

export interface V2AnswerResponse {
  correct: boolean;
  correct_index: number; // Index of correct answer (revealed after submit)
  explanation: string;
  theta_change: number;
  next_question: V2QuestionOut | null;
  session_stats: SessionStatsOut;
  session_ended: boolean;
}

/**
 * POST /api/rooms/classic/answer/{session_id} — Submit answer (secure, index-based)
 * Returns correct_index ONLY after submission, never before
 */
export const submitAnswerV2 = async (
  sessionId: string,
  params: V2AnswerRequest,
): Promise<V2AnswerResponse> => {
  const endpoint = `/api/rooms/classic/answer/${sessionId}`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      question_id: params.question_id,
      selected_index: params.selected_index,
      time_taken_seconds: params.time_taken_seconds,
      used_hint: params.used_hint,
    }),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  // Validate response structure
  if (typeof data !== 'object' || data === null) {
    throw new Error('Invalid response format from V2 answer API');
  }

  if (typeof data.correct !== 'boolean') {
    throw new Error('Invalid response: missing or invalid correct field');
  }

  if (typeof data.correct_index !== 'number') {
    throw new Error('Invalid response: missing or invalid correct_index');
  }

  if (typeof data.session_stats !== 'object') {
    throw new Error('Invalid response: missing session_stats');
  }

  return data as V2AnswerResponse;
};

export interface V2HintRequest {
  question_id: string;
}

export interface V2HintResponse {
  hint: string;
}

/**
 * POST /api/rooms/classic/hint/{session_id} — Get hint (secure)
 */
export const getHintV2 = async (
  sessionId: string,
  questionId: string,
): Promise<string> => {
  const endpoint = `/api/rooms/classic/hint/${sessionId}`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      question_id: questionId,
    }),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (typeof data !== 'object' || data === null) {
    throw new Error('Invalid response format from V2 hint API');
  }

  if (typeof data.hint !== 'string' || data.hint.trim().length === 0) {
    throw new Error('Invalid response: missing or invalid hint text');
  }

  return data.hint as string;
};

// ── CHALLENGE ENDPOINTS (Ranked competitive play) ───────────────────────────
// NOTE: ChallengeRank and ChallengeStatus types are imported from types.ts to avoid duplication

/**
 * GET /api/rooms/challenge/status — Get user's challenge status and rank
 */
export const getChallengeStatus = async (): Promise<ChallengeStatus> => {
  const endpoint = `/api/rooms/challenge/status`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: authHeaders(),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (!data.current_rank || typeof data.wins !== 'number') {
    throw new Error('Invalid challenge status response');
  }

  return data as ChallengeStatus;
};

// ────────────────────────────────────────────────────────────────────────────
// DEPRECATED V1 CHALLENGE ENDPOINTS
// ChallengeRoom.tsx now uses challengeService.ts for V2/MHD-style endpoints
// These functions are kept for potential backward compatibility
// TODO: Remove once confirmed no longer needed
// ────────────────────────────────────────────────────────────────────────────

export interface ChallengeStartRequest {
  rank_id: number;
  is_skip_attempt?: boolean;
}

export interface ChallengeStartResponse {
  match_id: string;
  rank: ChallengeRank;
  first_question: V2QuestionOut;
}

/**
 * @deprecated Use challengeService.startChallengeSession instead
 * POST /api/rooms/challenge/start — Start a ranked challenge match
 */
export const startChallengeMatch = async (req: ChallengeStartRequest): Promise<ChallengeStartResponse> => {
  const endpoint = `/api/rooms/challenge/start`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (!data.match_id || !data.first_question) {
    throw new Error('Invalid challenge start response');
  }

  return data as ChallengeStartResponse;
};

export interface ChallengeAnswerRequest {
  question_id: string;
  selected_index: number;
  time_taken_seconds: number;
}

export interface ChallengeAnswerResponse {
  correct: boolean;
  correct_index: number;  // Correct answer index (for learning)
  explanation: string;    // Explanation for the answer
  score_so_far: number;
  questions_remaining: number;
  next_question: V2QuestionOut | null;
}

/**
 * @deprecated Use challengeService.submitChallengeAnswer instead
 * POST /api/rooms/challenge/answer/{match_id} — Submit answer in challenge
 */
export const submitChallengeAnswer = async (
  matchId: string,
  req: ChallengeAnswerRequest,
): Promise<ChallengeAnswerResponse> => {
  const endpoint = `/api/rooms/challenge/answer/${matchId}`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (typeof data.correct !== 'boolean' || typeof data.score_so_far !== 'number') {
    throw new Error('Invalid challenge answer response');
  }

  return data as ChallengeAnswerResponse;
};

export interface QuestionReviewItem {
  question_text: string;
  options: string[];
  user_answer_index: number;
  correct_answer_index: number;
  was_correct: boolean;
  explanation: string;
}

export interface ChallengeEndResponse {
  result: 'win' | 'loss';
  score: number;
  rank_changed: boolean;
  new_rank: ChallengeRank | null;
  skip_result: 'promoted' | 'failed' | null;
  questions_review: QuestionReviewItem[];  // All Q&A for review
}

/**
 * @deprecated Use challengeService.endChallengeSession instead
 * POST /api/rooms/challenge/end/{match_id} — End a challenge match
 */
export const endChallengeMatch = async (matchId: string): Promise<ChallengeEndResponse> => {
  const endpoint = `/api/rooms/challenge/end/${matchId}`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (!data.result || typeof data.score !== 'number') {
    throw new Error('Invalid challenge end response');
  }

  return data as ChallengeEndResponse;
};

// ── CHALLENGE V2 ENDPOINTS (Dynamic Levels & Streaks) ───────────────────────
// NOTE: ChallengeRoom.tsx uses challengeService.ts, not these functions

/**
 * GET /api/rooms/challenge/v2/status — Get challenge status with V2 fields
 */
export const getChallengeStatusV2 = async (): Promise<ChallengeStatusV2> => {
  const endpoint = `/api/rooms/challenge/v2/status`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: authHeaders(),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (!data.current_rank || typeof data.rank_points !== 'number') {
    throw new Error('Invalid V2 challenge status response');
  }

  return data as ChallengeStatusV2;
};

/**
 * POST /api/rooms/challenge/v2/start — Start challenge with level selection
 */
export const startChallengeMatchV2 = async (req: ChallengeStartRequestV2): Promise<ChallengeMatchV2> => {
  const endpoint = `/api/rooms/challenge/v2/start`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (!data.match_id || !data.session_id || !data.first_question) {
    throw new Error('Invalid V2 challenge start response');
  }

  return data as ChallengeMatchV2;
};

export interface ChallengeAnswerRequestV2 {
  question_id: string;
  selected_index: number;
  time_taken_seconds?: number;  // Optional: server calculates if not provided
}

/**
 * POST /api/rooms/challenge/v2/answer/{match_id} — Submit answer with streaks
 */
export const submitChallengeAnswerV2 = async (
  matchId: string,
  req: ChallengeAnswerRequestV2,
): Promise<ChallengeAnswerResultV2> => {
  const endpoint = `/api/rooms/challenge/v2/answer/${matchId}`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (typeof data.correct !== 'boolean' || typeof data.points_change !== 'number') {
    throw new Error('Invalid V2 challenge answer response');
  }

  return data as ChallengeAnswerResultV2;
};

/**
 * POST /api/rooms/challenge/v2/end/{match_id} — End match with detailed stats
 */
export const endChallengeMatchV2 = async (matchId: string): Promise<ChallengeResultV2> => {
  const endpoint = `/api/rooms/challenge/v2/end/${matchId}`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (!data.result || typeof data.session_points !== 'number') {
    throw new Error('Invalid V2 challenge end response');
  }

  return data as ChallengeResultV2;
};

// ── CHALLENGE MHD-STYLE ENDPOINTS (separate question generation + answer by string) ────

/**
 * GET /api/rooms/challenge/v2/session/{sessionId} — Get session state
 */
export const getChallengeSessionState = async (sessionId: string): Promise<ChallengeSessionState> => {
  const endpoint = `/api/rooms/challenge/v2/session/${sessionId}`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: authHeaders(),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  return await response.json() as ChallengeSessionState;
};

export interface GenerateQuestionRequest {
  session_id: string;
  topic: TopicType;
  level: number;
}

/**
 * POST /api/rooms/challenge/v2/generate-question — Generate question at level
 */
export const generateChallengeQuestion = async (req: GenerateQuestionRequest): Promise<ChallengeQuestionMHD> => {
  const endpoint = `/api/rooms/challenge/v2/generate-question`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (!data.id || !data.text || !data.correctAnswer) {
    throw new Error('Invalid challenge question response');
  }

  return data as ChallengeQuestionMHD;
};

/**
 * POST /api/rooms/challenge/v2/submit-answer — Submit answer by string
 */
export const submitChallengeAnswerMHD = async (req: ChallengeSubmitAnswerRequest): Promise<ChallengeSubmitAnswerResponse> => {
  const endpoint = `/api/rooms/challenge/v2/submit-answer`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (typeof data.is_correct !== 'boolean' || typeof data.points_change !== 'number') {
    throw new Error('Invalid challenge answer response');
  }

  return data as ChallengeSubmitAnswerResponse;
};

/**
 * POST /api/rooms/challenge/v2/session/{sessionId}/end — End session (MHD-style)
 */
export const endChallengeSessionMHD = async (sessionId: string): Promise<ChallengeEndSessionResponse> => {
  const endpoint = `/api/rooms/challenge/v2/session/${sessionId}/end`;
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: authHeaders(),
  });

  if (!response.ok) {
    const err = await safeReadJson(response);
    throw handleApiError(response, err, endpoint);
  }

  const data = await response.json();

  if (!data.session_id || typeof data.total_points_earned !== 'number') {
    throw new Error('Invalid challenge end session response');
  }

  return data as ChallengeEndSessionResponse;
};
