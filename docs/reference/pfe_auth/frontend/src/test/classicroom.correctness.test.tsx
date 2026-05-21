import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, beforeEach, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

import ClassicRoom from '../pages/ClassicRoom';

const startQuizV2Mock = vi.fn();
const getHintV2Mock = vi.fn();
const submitAnswerV2Mock = vi.fn();

vi.mock('../services/apiService', () => ({
  startQuizV2: (...args: unknown[]) => startQuizV2Mock(...args),
  getHintV2: (...args: unknown[]) => getHintV2Mock(...args),
  submitAnswerV2: (...args: unknown[]) => submitAnswerV2Mock(...args),
}));

vi.mock('../components/InternalLayout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('../context/DevModeContext', () => ({
  useDevMode: () => ({ dev: { isEnabled: false, difficulty: 3, accuracy: 70, skipTimer: false } }),
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', username: 'tester', email: 'tester@example.com' }, logout: vi.fn() }),
}));

describe('ClassicRoom answer correctness behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getHintV2Mock.mockResolvedValue('Think about the most famous French city.');
  });

  it('marks exact correct option as correct', async () => {
    startQuizV2Mock.mockResolvedValueOnce({
      session_id: 's1',
      first_question: { id: 'q1', text: 'Capital of France?', options: ['Paris', 'Rome'], topic: 'history', difficulty: 2 },
      session_stats: { questions_answered: 0, correct_count: 0 },
    });
    submitAnswerV2Mock.mockResolvedValueOnce({
      correct: true,
      correct_index: 0,
      explanation: 'Paris is correct.',
      theta_change: 0.1,
      next_question: null,
      session_stats: { questions_answered: 1, correct_count: 1 },
      session_ended: false,
    });

    render(<MemoryRouter><ClassicRoom /></MemoryRouter>);
    await userEvent.click(screen.getByRole('button', { name: /History/i }));
    await userEvent.click(await screen.findByRole('button', { name: /Paris/i }));

    expect(screen.getByRole('button', { name: /Paris/i }).className).toContain('bg-green-50');
    expect(submitAnswerV2Mock).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({ question_id: 'q1', selected_index: 0 })
    );
  });

  it('marks normalized equivalent option as correct', async () => {
    startQuizV2Mock.mockResolvedValueOnce({
      session_id: 's2',
      first_question: { id: 'q2', text: 'Capital of France?', options: ['  PARIS  ', 'Rome'], topic: 'history', difficulty: 2 },
      session_stats: { questions_answered: 0, correct_count: 0 },
    });
    submitAnswerV2Mock.mockResolvedValueOnce({
      correct: true,
      correct_index: 0,
      explanation: 'Paris is correct.',
      theta_change: 0.1,
      next_question: null,
      session_stats: { questions_answered: 1, correct_count: 1 },
      session_ended: false,
    });

    render(<MemoryRouter><ClassicRoom /></MemoryRouter>);
    await userEvent.click(screen.getByRole('button', { name: /History/i }));
    await userEvent.click(await screen.findByRole('button', { name: /PARIS/i }));

    expect(screen.getByRole('button', { name: /PARIS/i }).className).toContain('bg-green-50');
    expect(submitAnswerV2Mock).toHaveBeenCalledWith(
      's2',
      expect.objectContaining({ question_id: 'q2', selected_index: 0 })
    );
  });

  it('marks truly wrong option as wrong', async () => {
    startQuizV2Mock.mockResolvedValueOnce({
      session_id: 's3',
      first_question: { id: 'q2b', text: 'Capital of France?', options: ['Paris', 'Rome'], topic: 'history', difficulty: 2 },
      session_stats: { questions_answered: 0, correct_count: 0 },
    });
    submitAnswerV2Mock.mockResolvedValueOnce({
      correct: false,
      correct_index: 0,
      explanation: 'Paris is correct.',
      theta_change: -0.1,
      next_question: null,
      session_stats: { questions_answered: 1, correct_count: 0 },
      session_ended: false,
    });

    render(<MemoryRouter><ClassicRoom /></MemoryRouter>);
    await userEvent.click(screen.getByRole('button', { name: /History/i }));
    await userEvent.click(await screen.findByRole('button', { name: /Rome/i }));

    expect(screen.getByRole('button', { name: /Rome/i }).className).toContain('bg-red-50');
    expect(submitAnswerV2Mock).toHaveBeenCalledWith(
      's3',
      expect.objectContaining({ question_id: 'q2b', selected_index: 1 })
    );
  });

  it('handles hint button and continue flow to summary actions', async () => {
    startQuizV2Mock
      .mockResolvedValueOnce({
        session_id: 's4',
        first_question: { id: 'q3', text: 'Q1', options: ['A', 'B'], topic: 'history', difficulty: 2 },
        session_stats: { questions_answered: 0, correct_count: 0 },
      });
    submitAnswerV2Mock.mockResolvedValueOnce({
      correct: true,
      correct_index: 0,
      explanation: 'E1',
      theta_change: 0.1,
      next_question: { id: 'q4', text: 'Q2', options: ['C', 'D'], topic: 'history', difficulty: 2 },
      session_stats: { questions_answered: 1, correct_count: 1 },
      session_ended: false,
    });

    render(<MemoryRouter><ClassicRoom /></MemoryRouter>);

    await userEvent.click(screen.getByRole('button', { name: /History/i }));

    await userEvent.click(await screen.findByRole('button', { name: /Get Hint/i }));
    expect(getHintV2Mock).toHaveBeenCalledWith('s4', 'q3');

    await userEvent.click(screen.getByRole('button', { name: /^A/i }));
    await userEvent.click(await screen.findByRole('button', { name: /Next Question/i }));

    expect(startQuizV2Mock).toHaveBeenCalledTimes(1);
    expect(await screen.findByText('Q2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^C/i }).className).not.toContain('bg-green-50');
    expect(screen.getByRole('button', { name: /^D/i }).className).not.toContain('bg-green-50');
    expect(screen.getByRole('button', { name: /^C/i }).className).not.toContain('bg-red-50');
    expect(screen.getByRole('button', { name: /^D/i }).className).not.toContain('bg-red-50');
  });
});
