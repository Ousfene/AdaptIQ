/**
 * Frontend configuration constants.
 * 
 * These values MUST stay in sync with backend/config.py.
 * When changing quiz rules, update both files!
 */

// ── Quiz / Game Rules ─────────────────────────────────────────────────────
// Must match QUIZ_TIME_LIMIT_SECONDS in backend/config.py
export const QUIZ_TIME_LIMIT = 30; // seconds per question

// Must match QUIZ_QUESTIONS_PER_SESSION in backend/config.py
export const QUIZ_TOTAL_QUESTIONS = 10;

// ── Points System ─────────────────────────────────────────────────────────
// Must match POINTS_* constants in backend/config.py
export const POINTS_BASE_AWARD = 10;
export const POINTS_TIME_BONUS_DIVISOR = 3;
export const POINTS_HINT_PENALTY = 3;
export const POINTS_WRONG_PENALTY = 5;

// ── API Configuration ─────────────────────────────────────────────────────
export const API_BASE = (() => {
  const url = import.meta.env.VITE_API_URL;
  if (!url) {
    throw new Error("VITE_API_URL environment variable is not configured");
  }
  // Enforce HTTPS in production
  if (import.meta.env.PROD && !url.startsWith("https://")) {
    throw new Error("Production environment requires HTTPS. API URL must start with https://");
  }
  return url;
})();
