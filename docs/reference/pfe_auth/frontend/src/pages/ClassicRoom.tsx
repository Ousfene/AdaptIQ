import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import InternalLayout from '../components/InternalLayout';
import { useDevMode } from '../context/DevModeContext';
import {
  ArrowLeft,
  Sparkle,
  ChevronRight,
  Flame,
  BookMarked,
  ShieldQuestion,
  Lightbulb,
  CheckCircle2,
  XCircle,
  Trophy,
  Loader2,
  BookOpen,
  ArrowRight,
  AlertTriangle,
} from 'lucide-react';
import { TopicType, Question, QuizSessionState } from '../types';
import { startQuizV2, submitAnswerV2, getHintV2, V2QuestionOut } from '../services/apiService';
import { QUIZ_TIME_LIMIT, QUIZ_TOTAL_QUESTIONS } from '../config';

const ClassicRoom: React.FC = () => {
  const navigate = useNavigate();
  const { dev } = useDevMode();
  const [step, setStep] = useState<'selection' | 'quiz' | 'summary'>('selection');
  const [topic, setTopic] = useState<TopicType | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [session, setSession] = useState<QuizSessionState | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);  // NOTE: Now index-based, not string
  const [isAnswered, setIsAnswered] = useState(false);
  const [questionEpoch, setQuestionEpoch] = useState(0);
  const [answeredQuestionEpoch, setAnsweredQuestionEpoch] = useState<number | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [isHintLoading, setIsHintLoading] = useState(false);
  const [timeLeft, setTimeLeft] = useState(QUIZ_TIME_LIMIT);
  const nextQuestionInFlightRef = useRef(false);
  const timeoutTriggeredRef = useRef(false);
  const pendingNextQuestionRef = useRef<V2QuestionOut | null>(null);

  // Timer effect with auto-submit on timeout
  useEffect(() => {
    let timer: NodeJS.Timeout;

    // Dev mode: skip timer goes instantly to 0
    if (step === 'quiz' && dev.skipTimer && !isAnswered && timeLeft > 0) {
      setTimeLeft(0);
      return;
    }

    if (step === 'quiz' && !isAnswered && timeLeft > 0) {
      timer = setInterval(() => {
        setTimeLeft((prev) => prev - 1);
      }, 1000);
    } else if (timeLeft === 0 && !isAnswered && !timeoutTriggeredRef.current && currentQuestion && session) {
      // Timeout: auto-submit with -1 index (no answer selected)
      // Mark as triggered immediately to prevent race conditions
      timeoutTriggeredRef.current = true;
      // Use setTimeout to ensure cleanup
      const submitTimeout = setTimeout(() => {
        handleAnswerSubmit(-1).catch((err) => {
          if (typeof console !== 'undefined') {
            console.error('Auto-submit failed:', err);
          }
        });
      }, 0);
      return () => {
        clearInterval(timer);
        clearTimeout(submitTimeout);
      };
    }
    return () => clearInterval(timer);
  }, [step, isAnswered, timeLeft, currentQuestion, session, dev.skipTimer]);

  // Timer security: show result after submission or at time limit
  useEffect(() => {
    if (timeLeft === 0 && isAnswered) {
      const timer = setTimeout(() => nextQuestion(), 2000);
      return () => clearTimeout(timer);
    }
  }, [timeLeft, isAnswered]);

  // ═══════ FE-6 FIX: Reset refs on unmount ═══════
  // Clear all refs when component unmounts to prevent stale state on re-mount
  useEffect(() => {
    return () => {
      nextQuestionInFlightRef.current = false;
      timeoutTriggeredRef.current = false;
      pendingNextQuestionRef.current = null;
    };
  }, []);
  // ═════════════════════════════════════════════════════════════

  const startSession = async (selectedTopic: TopicType) => {
    setIsLoading(true);
    setLoadError(null);
    setTopic(selectedTopic);
    timeoutTriggeredRef.current = false;
    try {
      const response = await startQuizV2(selectedTopic);
      if (response.first_question) {
        setCurrentQuestion(response.first_question);
        setSelectedIndex(null);
        setQuestionEpoch(0);
        setAnsweredQuestionEpoch(null);
        setIsAnswered(false);
        setHint(null);
        setTimeLeft(QUIZ_TIME_LIMIT);
        setSession({
          topic: selectedTopic,
          questions: [response.first_question],
          currentIndex: 0,
          score: 0,
          pointsEarned: 0,
          hintsUsed: 0,
          startTime: Date.now(),
          isFinished: false,
          sessionId: response.session_id,  // NEW: Store V2 session ID
        });
        setStep('quiz');
      } else {
        throw new Error('No first question returned from backend');
      }
    } catch (error: any) {
      setLoadError(error?.message ?? 'Failed to start session. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAnswerSubmit = async (index: number) => {
    // Don't allow if already answered, next question loading, or no session
    if (isAnswered || nextQuestionInFlightRef.current || !session || !currentQuestion) return;

    setSelectedIndex(index);
    setIsAnswered(true);
    setAnsweredQuestionEpoch(questionEpoch);
    nextQuestionInFlightRef.current = true;

    const timeTaken = QUIZ_TIME_LIMIT - timeLeft;

    try {
      const result = await submitAnswerV2(
        session.sessionId || '',
        {
          question_id: currentQuestion.id,
          selected_index: index,
          time_taken_seconds: timeTaken,
          used_hint: !!hint,
        }
      );

      // Update question with correct answer, correctIndex, and explanation (now SAFE - only after submission)
      setCurrentQuestion(prev => prev ? {
        ...prev,
        correctIndex: result.correct_index,
        explanation: result.explanation || '',  // Store explanation for "Learn More" display
      } : null);

      // Store the next question for when user clicks "Next Question"
      pendingNextQuestionRef.current = result.next_question;

      // Allow the "Next Question" button to be clicked
      nextQuestionInFlightRef.current = false;

      // Check if session ended
      if (result.session_ended) {
        setTimeout(() => setStep('summary'), 2000);
      }

      // Update session based on backend's correctness determination
      if (result.correct) {
        setSession(prev => prev ? {
          ...prev,
          score: prev.score + 1,
          pointsEarned: prev.pointsEarned + 10 + Math.floor(timeLeft / 3)
        } : null);
      } else {
        setSession(prev => prev ? {
          ...prev,
          pointsEarned: Math.max(0, prev.pointsEarned - 5)
        } : null);
      }
    } catch (err) {
      console.warn('submitAnswerV2 error:', err);
      setLoadError((err as any)?.message || 'Failed to submit answer');
      setIsAnswered(false);
      nextQuestionInFlightRef.current = false;
    }
  };

  const handleHint = async () => {
    if (!currentQuestion || hint || isHintLoading || !session) return;
    setIsHintLoading(true);
    try {
      const hintText = await getHintV2(
        session.sessionId || '',
        currentQuestion.id
      );
      setHint(hintText);
      setSession(prev => prev ? {
        ...prev,
        pointsEarned: prev.pointsEarned - 3,
        hintsUsed: prev.hintsUsed + 1
      } : null);
    } catch (error) {
      console.error("Failed to get hint:", error);
      setLoadError((error as any)?.message || 'Failed to load hint');
    } finally {
      setIsHintLoading(false);
    }
  };

  const nextQuestion = async () => {
    if (!session || !topic || nextQuestionInFlightRef.current) return;

    if (session.currentIndex >= QUIZ_TOTAL_QUESTIONS - 1) {
      setStep('summary');
      return;
    }

    // Load the next question that was pre-fetched during answer submission
    const nextQ = pendingNextQuestionRef.current;
    pendingNextQuestionRef.current = null;

    if (nextQ) {
      setCurrentQuestion({
        id: nextQ.id,
        text: nextQ.text,
        options: nextQ.options,
        explanation: '',
        difficulty: nextQ.difficulty,
      });
      setSelectedIndex(null);
      setAnsweredQuestionEpoch(null);
      setIsAnswered(false);
      setHint(null);
      setTimeLeft(QUIZ_TIME_LIMIT);
      setQuestionEpoch(prev => prev + 1);
      timeoutTriggeredRef.current = false;
      setSession(prev => prev ? {
        ...prev,
        currentIndex: prev.currentIndex + 1,
      } : null);
      nextQuestionInFlightRef.current = false;
    } else {
      // Fallback: start a fresh session call if no next question was provided
      setLoadError('No next question available. Session may have ended.');
      setStep('summary');
    }
  };

  if (step === 'selection') {
    return (
      <InternalLayout>
        <button onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-[#2D1B14]/60 hover:text-[#D4AF37] mb-12 transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </button>

        <div className="max-w-2xl mx-auto text-center">
          <div className="inline-block mb-8">
            <div className="flex items-center gap-3 px-5 py-2 border border-[#D4AF37]/40 rounded-full text-[11px] font-bold uppercase tracking-[0.4em] text-[#D4AF37]">
              <Sparkle className="w-3 h-3 fill-current" /> Classic Room
            </div>
          </div>

          <h1 className="text-5xl font-black font-playfair text-[#2D1B14] mb-6">Choose Your Path</h1>
          <p className="text-xl text-[#2D1B14]/60 italic mb-12">Select the domain of knowledge you wish to explore today.</p>

          {loadError && (
            <div className="flex items-center gap-3 p-4 mb-8 bg-red-50 border border-red-200 text-red-700 text-sm">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <span>{loadError}</span>
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 mb-12">
            {[
              { id: 'History' as TopicType, icon: <BookMarked className="w-6 h-6" />, desc: 'Delve into the chronicles of human civilization.' },
              { id: 'Geography' as TopicType, icon: <ShieldQuestion className="w-6 h-6" />, desc: 'Master the logic of shapes and space.' },
              { id: 'Mixed' as TopicType, icon: <Flame className="w-6 h-6" />, desc: 'A broad examination of various scholarly disciplines.' }
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => startSession(t.id)}
                disabled={isLoading}
                className="group relative bg-white p-8 border border-[#2D1B14]/10 hover:border-[#D4AF37] transition-all text-left flex items-center gap-8 shadow-sm hover:shadow-xl disabled:opacity-60"
              >
                <div className="w-16 h-16 bg-[#F5F2E7] flex items-center justify-center text-[#2D1B14] group-hover:bg-[#2D1B14] group-hover:text-[#D4AF37] transition-all">
                  {t.icon}
                </div>
                <div>
                  <div className="text-xl font-black font-playfair text-[#2D1B14]">{t.id}</div>
                  <div className="text-sm italic text-[#2D1B14]/60">{t.desc}</div>
                </div>
                <ChevronRight className="ml-auto w-6 h-6 text-[#D4AF37] opacity-0 group-hover:opacity-100 transition-all" />
              </button>
            ))}
          </div>

          {isLoading && (
            <div className="flex items-center justify-center gap-3 text-[#D4AF37] font-bold uppercase tracking-widest text-xs">
              <Loader2 className="w-5 h-5 animate-spin" /> Preparing the Archives...
            </div>
          )}
        </div>
      </InternalLayout>
    );
  }

  if (step === 'quiz' && currentQuestion && session) {
    const hasCommittedAnswer = (
      isAnswered
      && selectedIndex !== null
      && answeredQuestionEpoch === questionEpoch
    );
    const questionLocked = hasCommittedAnswer || timeLeft === 0 || isLoading;
    const correctIndex = currentQuestion.correctIndex;
    const showCorrectAnswer = isAnswered && correctIndex !== undefined;

    return (
      <InternalLayout>
        <div className="max-w-3xl mx-auto">
          {/* Quiz Header */}
          <div className="flex justify-between items-center mb-12 pb-6 border-b border-[#D4AF37]/20">
            <div className="flex items-center gap-4">
              <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#D4AF37]">Question {session.currentIndex + 1} / {QUIZ_TOTAL_QUESTIONS}</div>
              <div className="w-32 h-1 bg-[#2D1B14]/5 rounded-full overflow-hidden">
                <div className="h-full bg-[#D4AF37] transition-all" style={{ width: `${(session.currentIndex + 1) * 10}%` }} />
              </div>
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-green-600">
                {session.score} correct
              </div>
            </div>

            <div className="flex items-center gap-8">
              <div className="text-center">
                <div className="text-xs font-bold uppercase tracking-widest opacity-40">Timer</div>
                <div className={`text-xl font-black font-mono ${timeLeft <= 5 ? 'text-red-500 animate-pulse' : 'text-[#2D1B14]'}`}>
                  {timeLeft}s
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs font-bold uppercase tracking-widest opacity-40">Points</div>
                <div className="text-xl font-black text-[#D4AF37]">{session.pointsEarned}</div>
              </div>
            </div>
          </div>

          {loadError && (
            <div className="flex items-center gap-3 p-4 mb-8 bg-red-50 border border-red-200 text-red-700 text-sm">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <span>{loadError}</span>
            </div>
          )}

          {/* Question Text */}
          <div className="mb-10">
            <h2 className="text-2xl font-playfair text-[#2D1B14] mb-6">{currentQuestion.text}</h2>
          </div>

          {/* Answer Options */}
          <div className="space-y-4 mb-10">
            {currentQuestion.options.map((option, idx) => {
              const isSelected = selectedIndex === idx;
              const isCorrect = showCorrectAnswer && idx === correctIndex;
              const isWrong = showCorrectAnswer && isSelected && idx !== correctIndex;

              return (
                <button
                  key={idx}
                  onClick={() => {
                    if (!questionLocked) {
                      setSelectedIndex(idx);
                      handleAnswerSubmit(idx);
                    }
                  }}
                  disabled={questionLocked}
                  className={`
                    w-full p-5 text-left border-2 transition-all flex items-start gap-4
                    ${!questionLocked && !isSelected ? 'border-[#2D1B14]/10 hover:border-[#D4AF37] cursor-pointer' : ''}
                    ${isSelected && !isCorrect && !isWrong ? 'border-[#D4AF37] bg-[#D4AF37]/5' : ''}
                    ${isCorrect ? 'border-green-500 bg-green-50' : ''}
                    ${isWrong ? 'border-red-500 bg-red-50' : ''}
                    ${questionLocked && !isSelected ? 'opacity-60' : ''}
                  `}
                >
                  <div className={`
                    flex-shrink-0 w-6 h-6 rounded-full border-2 flex items-center justify-center mt-0.5
                    ${isCorrect ? 'border-green-500 bg-green-500' : ''}
                    ${isWrong ? 'border-red-500 bg-red-500' : ''}
                    ${!isCorrect && !isWrong && isSelected ? 'border-[#D4AF37] bg-[#D4AF37]' : ''}
                    ${!isCorrect && !isWrong && !isSelected ? 'border-[#2D1B14]/20' : ''}
                  `}>
                    {isCorrect && <CheckCircle2 className="w-4 h-4 text-white" />}
                    {isWrong && <XCircle className="w-4 h-4 text-white" />}
                  </div>
                  <div className="flex-grow">
                    <div className={`
                      font-medium
                      ${isCorrect ? 'text-green-700' : ''}
                      ${isWrong ? 'text-red-700' : ''}
                      ${!isCorrect && !isWrong ? 'text-[#2D1B14]' : ''}
                    `}>
                      {option}
                    </div>
                  </div>
                  {isCorrect && <span className="flex-shrink-0 text-green-700 font-bold">Correct</span>}
                  {isWrong && <span className="flex-shrink-0 text-red-700 font-bold">Wrong</span>}
                </button>
              );
            })}
          </div>

          {/* Hint Button */}
          {!isAnswered && (
            <button
              onClick={handleHint}
              disabled={isHintLoading || !!hint}
              className="flex items-center gap-2 px-4 py-2 bg-[#D4AF37]/10 hover:bg-[#D4AF37]/20 disabled:opacity-50 text-[#D4AF37] text-sm font-bold uppercase tracking-widest transition-all mb-8"
            >
              <Lightbulb className="w-4 h-4" /> {hint ? 'Hint Used' : 'Get Hint'} {isHintLoading && <Loader2 className="w-4 h-4 animate-spin" />}
            </button>
          )}

          {hint && (
            <div className="p-4 mb-8 bg-[#D4AF37]/5 border border-[#D4AF37]/20 italic text-[#2D1B14]/80 text-sm">
              💡 {hint}
            </div>
          )}

          {/* Learn More / Explanation - shown after answering */}
          {hasCommittedAnswer && currentQuestion.explanation && (
            <div className="p-5 mb-8 bg-blue-50/50 border border-blue-200 text-[#2D1B14]">
              <div className="flex items-center gap-2 mb-3">
                <BookOpen className="w-5 h-5 text-blue-600" />
                <span className="text-sm font-bold uppercase tracking-widest text-blue-600">Learn More</span>
              </div>
              <p className="text-sm leading-relaxed text-[#2D1B14]/80">{currentQuestion.explanation}</p>
            </div>
          )}

          {/* Next Button */}
          {hasCommittedAnswer && (
            <div className="flex gap-4 items-center">
              <button
                onClick={nextQuestion}
                disabled={isLoading}
                className="flex items-center gap-2 px-6 py-3 bg-[#D4AF37] hover:bg-[#D4AF37]/90 disabled:opacity-50 text-[#2D1B14] font-bold uppercase tracking-widest transition-all"
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                Next Question
              </button>
              {session.currentIndex === QUIZ_TOTAL_QUESTIONS - 1 && (
                <span className="text-sm text-[#2D1B14]/60">Final question</span>
              )}
            </div>
          )}
        </div>
      </InternalLayout>
    );
  }

  if (step === 'summary' && session) {
    const accuracy = session.score / QUIZ_TOTAL_QUESTIONS;
    const scoreColor = accuracy > 0.7 ? 'text-green-600' : accuracy > 0.5 ? 'text-yellow-600' : 'text-red-600';

    return (
      <InternalLayout>
        <div className="max-w-2xl mx-auto text-center">
          <Trophy className="w-20 h-20 mx-auto mb-8 text-[#D4AF37]" />

          <h1 className="text-5xl font-black font-playfair text-[#2D1B14] mb-6">Quiz Complete!</h1>

          <div className={`text-4xl font-black font-mono mb-8 ${scoreColor}`}>
            {session.score} / {QUIZ_TOTAL_QUESTIONS}
          </div>

          <div className="grid grid-cols-3 gap-6 mb-12">
            <div className="p-6 bg-white border border-[#2D1B14]/10">
              <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#2D1B14]/60 mb-2">Accuracy</div>
              <div className="text-2xl font-black text-[#2D1B14]">{Math.round(accuracy * 100)}%</div>
            </div>
            <div className="p-6 bg-white border border-[#2D1B14]/10">
              <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#2D1B14]/60 mb-2">Points</div>
              <div className="text-2xl font-black text-[#D4AF37]">{session.pointsEarned}</div>
            </div>
            <div className="p-6 bg-white border border-[#2D1B14]/10">
              <div className="text-[10px] font-bold uppercase tracking-[0.3em] text-[#2D1B14]/60 mb-2">Hints</div>
              <div className="text-2xl font-black text-[#2D1B14]">{session.hintsUsed}</div>
            </div>
          </div>

          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center justify-center gap-2 px-8 py-4 bg-[#D4AF37] hover:bg-[#D4AF37]/90 text-[#2D1B14] font-bold uppercase tracking-widest transition-all"
          >
            <ArrowLeft className="w-5 h-5" /> Return to Dashboard
          </button>
        </div>
      </InternalLayout>
    );
  }

  return null;
};

export default ClassicRoom;
