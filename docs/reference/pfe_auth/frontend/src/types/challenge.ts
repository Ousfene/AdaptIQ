/**
 * src/types/challenge.ts
 *
 * TypeScript types for the Challenge Room.
 * Adapted from MHD version with Main backend rank names.
 */

// ── Rank system ──────────────────────────────────────────────────────────

/** Main backend rank names (Bronze → Diamond) */
export type Rank = 'Bronze' | 'Silver' | 'Gold' | 'Platinum' | 'Diamond';

/** Challenge levels 1-5 */
export type ChallengeLevel = 1 | 2 | 3 | 4 | 5;

/** Topic type */
export type TopicType = 'History' | 'Geography' | 'Mixed';

/** Rank display labels */
export const RANK_LABELS: Record<Rank, string> = {
  'Bronze': 'Novice',
  'Silver': 'Apprentice',
  'Gold': 'Scholar',
  'Platinum': 'Master',
  'Diamond': 'Grandmaster'
};

/** Rank badge letters for UI */
export const RANK_BADGES: Record<Rank, string> = {
  'Bronze': 'E',
  'Silver': 'D',
  'Gold': 'C',
  'Platinum': 'B',
  'Diamond': 'A'
};

/** Level badge letters */
export const LEVEL_BADGES: Record<ChallengeLevel, string> = {
  1: 'E', 2: 'D', 3: 'C', 4: 'B', 5: 'A'
};


// ── API response shapes (match backend schemas) ───────────────────────────

/**
 * GET /api/rooms/challenge/v2/status
 * Backend: ChallengeStatusResponseV2
 */
export interface UserRank {
  current_rank: {
    id: number;
    name: Rank;
    n_options: number;
    has_timer: boolean;
    timer_seconds: number | null;
  };
  can_skip_up: boolean;
  skip_attempts_remaining: number;
  wins: number;
  losses: number;
  classic_games_played: number;
  rank_points: number;
  highest_streak: number;
  total_sessions: number;
  available_levels: ChallengeLevel[];
}

/**
 * POST /api/rooms/challenge/v2/start
 * Backend: ChallengeStartResponseV2
 */
export interface StartSessionResponse {
  match_id: string;
  session_id: string;
  current_level: ChallengeLevel;
  rank_points: number;
  available_levels: ChallengeLevel[];
  current_rank: {
    id: number;
    name: Rank;
    n_options: number;
    has_timer: boolean;
    timer_seconds: number | null;
  };
  topic: TopicType;
  first_question: ChallengeQuestion;
}

/**
 * POST /api/rooms/challenge/v2/generate-question
 * Backend: ChallengeQuestionOut
 */
export interface ChallengeQuestion {
  id: string;
  text: string;
  options: string[];
  correctAnswer: string;
  explanation: string;
  level: ChallengeLevel;
  points_value: number;
  is_free_text: boolean;
}

/**
 * Forced level change signal
 * Backend: ForceLevelChange
 */
export interface ForceLevelChange {
  direction: 'up' | 'down';
  reason: string;
}

/**
 * POST /api/rooms/challenge/v2/submit-answer
 * Backend: ChallengeSubmitAnswerResponse
 */
export interface SubmitAnswerResponse {
  is_correct: boolean;
  points_change: number;
  new_rank_points: number;
  new_level: ChallengeLevel;
  streak_correct: number;
  streak_wrong: number;
  force_level_change: ForceLevelChange | null;
}

/**
 * POST /api/rooms/challenge/v2/session/{id}/end
 * Backend: ChallengeEndSessionResponse
 */
export interface EndSessionResponse {
  session_id: string;
  total_questions: number;
  correct_answers: number;
  total_points_earned: number;
  new_rank: Rank;
  new_rank_points: number;
  rank_changed: boolean;
}


// ── Frontend session state (held in React useState) ──────────────────────

/**
 * Full in-memory session state managed by ChallengeRoom.tsx.
 */
export interface ChallengeSessionState {
  session_id: string;
  match_id: string;
  topic: TopicType;
  current_level: ChallengeLevel;
  current_rank: Rank;
  rank_points: number;
  streak_correct: number;
  streak_wrong: number;
  questions: ChallengeQuestion[];
  currentIndex: number;
  score: number;
  pointsEarned: number;
  force_level_change: ForceLevelChange | null;
  available_levels: ChallengeLevel[];
}
