// src/types.ts

// ── IMPORTANT: 'Geography' not 'Geometry' — must match backend ───────────
export type TopicType = 'Geography' | 'History' | 'Mixed';

export interface Question {
  id: string;
  text: string;
  options: string[];
  correctAnswer: string;
  explanation: string;
  image?: string;          // optional — backend doesn't send this
  topic?: TopicType;       // optional — backend doesn't send this
  difficulty?: number;     // optional — backend doesn't send this
}

export interface UserStats {
  id: string;
  points: number;
  level: string;
  totalQuestions: number;
  globalAccuracy: number;
  dailyQuestions: number;
  dailyAccuracy: number;
  learningTimeMinutes: number;
}

export interface RoomProgress {
  id: string;
  name: string;
  description: string;
  progress: number;
  isLocked: boolean;
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
}