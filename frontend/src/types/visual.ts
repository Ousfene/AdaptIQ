import type { TopicType } from '../types';

export type VisualQuestionType = 'M' | 'T';

export interface VisualQuestion {
  id: string;
  image_url: string;
  text: string;
  options: string[];
  topic: TopicType;
  level: number;
  question_type: VisualQuestionType;
  options_count: number;
  shape_svg: string | null;
  show_flag: boolean;
  show_shape: boolean;
}

export interface StartVisualSessionResponse {
  session_id: string;
  topic: TopicType;
  level: number;
  total_questions: number;
}

export interface SubmitVisualAnswerResponse {
  is_correct: boolean;
  correct_answer: string;
  explanation: string;
  next_question: VisualQuestion | null;
}

export interface VisualEndSessionResponse {
  session_id: string;
  topic: TopicType;
  level: number;
  score: number;
  questions_seen: number;
  total_questions: number;
  accuracy_percent: number;
}
