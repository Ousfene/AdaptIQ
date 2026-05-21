/**
 * services/apiService.ts
 * 
 * Drop-in replacement for geminiService.ts — calls the FastAPI backend.
 * 
 * USAGE: In ClassicRoom.tsx, replace:
 *   import { generateQuestion, generateHint } from '../services/geminiService';
 * with:
 *   import { generateQuestion, generateHint } from '../services/apiService';
 * 
 * Also add submitAnswer() call inside handleAnswer():
 *   await submitAnswer({ user_id, session_id, question_id, selected_answer, time_taken, used_hint });
 */

import { Question, TopicType } from '../types';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ── Session tracking (persisted per browser session) ─────────────────────
const getSessionId = (): string => {
  let id = sessionStorage.getItem('adaptiq_session_id');
  /* Retrieving the value stored in the 'adaptiq_session_id' key from the sessionStorage. If the value
  is not found, it initializes the variable 'id' with a new unique identifier generated using
  `crypto.randomUUID()` and then stores this new value in the 'adaptiq_session_id' key in the
  sessionStorage for future use. */
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem('adaptiq_session_id', id);
  }
  return id;
};

const getUserId = (): string => {
  let id = localStorage.getItem('adaptiq_user_id');
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem('adaptiq_user_id', id);
  }
  return id;
};

// Reset session ID at start of each quiz (new session per ClassicRoom run)
export const resetSession = (): string => {
  const newId = crypto.randomUUID();
  sessionStorage.setItem('adaptiq_session_id', newId);
  return newId;
};


// ── POST /api/classic/generate-question ──────────────────────────────────
export const generateQuestion = async (
  topic: TopicType,
  difficulty: number,
): Promise<Question> => {
  const response = await fetch(`${API_BASE}/api/classic/generate-question`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      topic,
      difficulty: Math.max(1, Math.min(5, Math.round(difficulty))),
      user_id: getUserId(),
      session_id: getSessionId(),
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${response.status}`);
  }

  const data = await response.json();

  // Validate shape matches TS Question interface
  if (!data.id || !data.text || !Array.isArray(data.options) || !data.correctAnswer) {
    throw new Error('Invalid question format from API');
  }

  return data as Question;
};


// ── POST /api/classic/generate-hint ──────────────────────────────────────
export const generateHint = async (
  questionText: string,
  correctAnswer: string,
): Promise<string> => {
  const response = await fetch(`${API_BASE}/api/classic/generate-hint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ questionText, correctAnswer }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${response.status}`);
  }

  const data = await response.json();
  return data.hint as string;
};


// ── POST /api/classic/submit-answer ──────────────────────────────────────
export interface SubmitAnswerParams {
  question_id: string;
  selected_answer: string;
  time_taken: number;      // seconds taken to answer
  used_hint: boolean;
}

export interface SubmitAnswerResult {
  success: boolean;
  updated_difficulty: number;
}

export const submitAnswer = async (
  params: SubmitAnswerParams,
): Promise<SubmitAnswerResult> => {
  const response = await fetch(`${API_BASE}/api/classic/submit-answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
    // Non-fatal — don't block the UI
    console.warn('submit-answer failed:', response.status);
    return { success: false, updated_difficulty: 2 };
  }

  return await response.json() as SubmitAnswerResult;
};


// ── Health check utility ──────────────────────────────────────────────────
export const checkApiHealth = async (): Promise<boolean> => {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
};