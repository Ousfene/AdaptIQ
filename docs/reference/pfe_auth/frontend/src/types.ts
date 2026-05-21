// src/types.ts

// ── IMPORTANT: Frontend uses PascalCase for display, but API expects lowercase ─────
// Use normalizeTopicForApi() before sending to backend
export type TopicType = 'Geography' | 'History' | 'Mixed';

// Convert TopicType to API-expected lowercase format
export const normalizeTopicForApi = (topic: TopicType): string => {
  const mapping: Record<TopicType, string> = {
    'Geography': 'geography',
    'History': 'history',
    'Mixed': 'mix',
  };
  return mapping[topic] || topic.toLowerCase();
};

export interface Question {
  id: string;
  text: string;
  options: string[];
  correctAnswer?: string;  // Only available after answer submission (security fix)
  correctIndex?: number;   // NEW: Index of correct answer (V2 API returns this AFTER submission)
  explanation: string;
  locked?: boolean;          // NEW: True = UI locked, False = can accept answers
  image?: string;          // optional — backend doesn't send this
  topic?: TopicType;       // optional — backend doesn't send this
  difficulty?: number;     // optional — backend doesn't send this
}

export interface UserStats {
  id: string;
  points: number;
  level: string;
  total_questions: number;      // snake_case to match backend response
  correct_questions: number;    // snake_case to match backend response
  global_accuracy: number;      // snake_case to match backend response
  daily_questions: number;      // snake_case to match backend response
  daily_correct: number;        // snake_case to match backend response
  daily_accuracy: number;       // snake_case to match backend response
  learning_time_minutes: number; // snake_case to match backend response
}

export interface RoomProgress {
  id: string;
  name: string;
  description: string;
  progress: number;
  isLocked: boolean;
  path?: string;
}

export interface QuizSessionState {
  topic: TopicType;
  questions: Question[];
  currentIndex: number;
  score: number;
  pointsEarned: number;
  hintsUsed: number;
  startTime: number;
  isFinished: boolean;
  sessionId?: string;  // NEW: V2 session ID for /answer/{sessionId} endpoint
}

export interface TopicStats {
  topic: TopicType;
  total_questions: number;
  correct_questions: number;
  accuracy: number;
  hints_used: number;
  avg_time_seconds: number;
}

export interface TopicBreakdown {
  topics: TopicStats[];
}

export interface DailyTrendPoint {
  date: string;
  total_questions: number;
  correct_questions: number;
  accuracy: number;
  avg_time_seconds: number;
}

export interface DailyTrend {
  days: number;
  points: DailyTrendPoint[];
}

export interface RedisOpsStats {
  status: string;
  active_sessions: number;
  session_ttl_buckets: Record<string, number>;
  otp_keys: number;
  rate_limit_keys: number;
  revoked_token_keys: number;
}

// ── Concept-Based Mastery (Phase 2) ────────────────────────────────────────

export type MasteryLevel = 'Beginner' | 'Intermediate' | 'Advanced';

export interface ConceptMastery {
  concept: string;           // Concept name (e.g., "Roman Empire")
  theta: number;             // IRT ability estimate [-3, 3]
  level: MasteryLevel;       // Derived from theta ranges
  responses: number;         // How many answers calibrated this theta
  lastUpdated: string;       // ISO timestamp
}

export interface ConceptBreakdown {
  concepts: Record<string, ConceptMastery[]>;  // Grouped by topic (e.g., "History" → [...])
}

// ── Challenge Room (Competitive Rank System) ───────────────────────────────

export type ChallengeRankName = 'Bronze' | 'Silver' | 'Gold' | 'Platinum' | 'Diamond';

export interface ChallengeRank {
  id: number;
  name: ChallengeRankName;
  n_options: number;          // Number of MC options at this rank
  has_timer: boolean;          // Whether timer is enabled
  timer_seconds: number | null; // Seconds per question (null if no timer)
}

export interface ChallengeStatus {
  current_rank: ChallengeRank;
  can_skip_up: boolean;
  skip_attempts_remaining: number;
  wins: number;
  losses: number;
  classic_games_played: number;
}

// ────────────────────────────────────────────────────────────────────────────
// DEPRECATED V1 CHALLENGE TYPES
// These are no longer used by ChallengeRoom.tsx (now uses types/challenge.ts)
// Kept for backward compatibility with apiService.ts V1 endpoints
// TODO: Remove these once V1 challenge endpoints are removed from backend
// ────────────────────────────────────────────────────────────────────────────

/** @deprecated Use types/challenge.ts instead */
export interface ChallengeMatch {
  match_id: string;
  rank: ChallengeRank;
  first_question: Question;
  questions_answered: number;
  correct_count: number;
}

/** @deprecated Use types/challenge.ts instead */
export interface ChallengeAnswerResult {
  correct: boolean;
  correct_index: number;
  next_question: Question | null;
  questions_answered: number;
  correct_count: number;
  match_ended: boolean;
}

/** @deprecated Use types/challenge.ts instead */
export interface ChallengeResult {
  match_id: string;
  rank: ChallengeRank;
  new_rank: ChallengeRank | null;
  accuracy: number;
  won: boolean;
  questions_answered: number;
  correct_count: number;
}

// ── Challenge Room V2 (Dynamic Levels & Streaks) ────────────────────────────
// NOTE: ChallengeRoom.tsx uses types/challenge.ts, not these V2 types

/** @deprecated Use types/challenge.ts UserRank instead */
export interface ChallengeStatusV2 extends ChallengeStatus {
  rank_points: number;         // Total points toward next rank
  highest_streak: number;      // Best ever correct streak
  total_sessions: number;      // Total challenge sessions played
  available_levels: number[];  // Which levels this rank can access (e.g., [1,2] for Bronze)
}

export interface ChallengeStartRequestV2 {
  topic: TopicType;
  starting_level?: number;     // 1-5, defaults to rank's lowest
}

export interface ChallengeMatchV2 {
  match_id: string;
  session_id: string;          // V2: tracks dynamic session state
  current_level: number;
  rank_points: number;         // Session points so far
  available_levels: number[];
  current_rank: ChallengeRank;
  topic: TopicType;
  first_question: Question;
}

export interface LevelChangeInfo {
  direction: 'up' | 'down';
  reason: string;
  old_level: number;
  new_level: number;
}

export interface ChallengeAnswerResultV2 {
  correct: boolean;
  correct_index: number;
  explanation: string;
  // V2 additions
  points_change: number;       // Points gained/lost this question
  new_rank_points: number;     // Total session points after this answer
  new_level: number;           // Current level (may have changed)
  streak_correct: number;      // Current consecutive correct
  streak_wrong: number;        // Current consecutive wrong
  level_change: LevelChangeInfo | null;  // If streak triggered a level change
  // Standard fields
  questions_remaining: number;
  next_question: Question | null;
  match_ended: boolean;
}

export interface ChallengeResultV2 {
  result: 'win' | 'loss';
  score: number;
  rank_changed: boolean;
  new_rank: ChallengeRank | null;
  skip_result: 'promoted' | 'failed' | null;
  questions_review: QuestionReviewItem[];
  // V2 additions
  session_points: number;      // Points earned this session
  total_rank_points: number;   // New total rank points
  highest_streak: number;      // Best streak this session
  level_changes_count: number; // How many times level changed
}

export interface QuestionReviewItem {
  question_text: string;
  options: string[];
  user_answer_index: number;
  correct_answer_index: number;
  was_correct: boolean;
  explanation: string;
}

// ── Challenge Room MHD-Style Types ──────────────────────────────────────────

export interface ChallengeQuestionMHD {
  id: string;
  text: string;
  options: string[];
  correctAnswer: string;  // Visible for immediate feedback
  explanation: string;
  level: number;
  points_value: number;   // Points if answered correctly
  is_free_text: boolean;
}

export interface ChallengeSubmitAnswerRequest {
  session_id: string;
  question_id: string;
  answer: string;         // Answer string (not index)
  time_taken?: number;
}

export interface ForceLevelChange {
  direction: 'up' | 'down';
  reason: string;
}

export interface ChallengeSubmitAnswerResponse {
  is_correct: boolean;
  points_change: number;      // Signed value (+3 or -1, etc.)
  new_rank_points: number;    // Session running total
  new_level: number;
  streak_correct: number;
  streak_wrong: number;
  force_level_change: ForceLevelChange | null;
}

export interface ChallengeSessionState {
  session_id: string;
  user_id: string;
  topic: string;
  starting_level: number;
  current_level: number;
  rank_points: number;
  streak_correct: number;
  streak_wrong: number;
  total_questions: number;
  correct_answers: number;
  is_completed: boolean;
}

export interface ChallengeEndSessionResponse {
  session_id: string;
  total_questions: number;
  correct_answers: number;
  total_points_earned: number;
  new_rank: string;           // Bronze/Silver/Gold/Platinum/Diamond
  new_rank_points: number;    // Global cumulative
  rank_changed: boolean;
}