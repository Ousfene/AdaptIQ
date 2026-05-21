/**
 * services/visualRoomService.ts
 * All API calls for the VisualRoom — matches routers/visual_room.py exactly.
 *
 * KEY FIX vs original frontend:
 *   - fetchNextVisualQuestion takes session_id + user_id (not just topic/level)
 *   - submitVisualAnswer takes session_id + user_id
 *   - generateHint uses /api/visual/hint?question_id=... (no correct answer exposed)
 *   - correct answer is never stored in the VisualQuestion type returned from /next
 */

import type { TopicType } from '../types';
import type {
  VisualQuestion,
  StartVisualSessionResponse,
  SubmitVisualAnswerResponse,
  VisualEndSessionResponse,
} from '../types/visual';
import { notifyDashboardStatsUpdated } from './dashboardEvents';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ── Auth helpers (match other rooms) ─────────────────────────────────────────

const getUserId = (): string => {
  // Prefer the canonical key used by Classic/Challenge/Custom.
  let id = localStorage.getItem('adaptiq_user_id');
  if (!id) {
    // Back-compat: some screens used `user_id`.
    id = localStorage.getItem('user_id') ?? '';
  }
  if (!id) {
    id = crypto.randomUUID();
  }
  // Keep both keys in sync so older code continues to work.
  localStorage.setItem('adaptiq_user_id', id);
  localStorage.setItem('user_id', id);
  return id;
};

// ─── Types ────────────────────────────────────────────────────────────────────

export type { StartVisualSessionResponse, SubmitVisualAnswerResponse, VisualQuestion, VisualEndSessionResponse };

// ─── Start session ────────────────────────────────────────────────────────────

export async function startVisualSession(
  topic: TopicType,
  level: number
): Promise<StartVisualSessionResponse> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/api/visual/start-session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, topic, level }),
  });
  if (!res.ok) throw new Error(`start-session failed: ${res.status}`);
  return res.json();
}

// ─── Fetch next question (no correct answer in response) ─────────────────────

export async function fetchNextVisualQuestion(
  sessionId: string,
): Promise<VisualQuestion> {
  const params = new URLSearchParams({
    session_id: sessionId,
  });
  const res = await fetch(`${API_BASE}/api/visual/next?${params}`);
  if (!res.ok) throw new Error(`fetch next failed: ${res.status}`);
  return res.json();
}

// ─── Submit answer ────────────────────────────────────────────────────────────

export async function submitVisualAnswer(
  sessionId: string,
  questionId: string,
  chosenAnswer: string,
  userTimeMs?: number
): Promise<SubmitVisualAnswerResponse> {
  const userId = getUserId();
  const res = await fetch(`${API_BASE}/api/visual/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id:    sessionId,
      question_id:   questionId,
      user_id:       userId,
      chosen_answer: chosenAnswer,
      user_time_ms:  userTimeMs,
    }),
  });
  if (!res.ok) throw new Error(`submit failed: ${res.status}`);
  const data = await res.json();
  notifyDashboardStatsUpdated();
  return data;
}

// ─── Hint (uses question_id only — correct answer never sent to frontend) ─────

export async function fetchVisualHint(questionId: string): Promise<string> {
  const params = new URLSearchParams({ question_id: questionId });
  const res = await fetch(`${API_BASE}/api/visual/hint?${params}`);
  if (!res.ok) throw new Error(`hint fetch failed: ${res.status}`);
  const data = await res.json();
  return data.hint as string;
}

// ─── End session ──────────────────────────────────────────────────────────────

export async function endVisualSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/visual/session/${sessionId}/end`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`end session failed: ${res.status}`);
  return res.json() as Promise<VisualEndSessionResponse>;
}
