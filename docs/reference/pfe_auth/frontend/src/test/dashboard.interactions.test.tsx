import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';

import Dashboard from '../pages/Dashboard';

const fetchUserStatsMock = vi.fn();
const fetchUserTopicBreakdownMock = vi.fn();
const fetchUserDailyTrendMock = vi.fn();
const fetchRedisOpsStatsMock = vi.fn();

vi.mock('../services/apiService', () => ({
  fetchUserStats: () => fetchUserStatsMock(),
  fetchUserTopicBreakdown: () => fetchUserTopicBreakdownMock(),
  fetchUserDailyTrend: () => fetchUserDailyTrendMock(),
  fetchRedisOpsStats: () => fetchRedisOpsStatsMock(),
}));

vi.mock('../components/InternalLayout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

describe('Dashboard interactions and resilience UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchUserTopicBreakdownMock.mockResolvedValue({ topics: [] });
    fetchUserDailyTrendMock.mockResolvedValue({ days: [] });
    fetchRedisOpsStatsMock.mockResolvedValue({
      status: 'ok',
      active_sessions: 1,
      session_ttl_buckets: { lt_5m: 0, '5m_to_30m': 1, gt_30m: 0, unknown: 0 },
      otp_keys: 0,
      rate_limit_keys: 0,
      revoked_token_keys: 0,
    });
  });

  it('renders live user stats cards when API succeeds', async () => {
    fetchUserStatsMock.mockResolvedValueOnce({
      id: 'u1',
      points: 120,
      level: 'Adept',
      total_questions: 40,
      correct_questions: 30,
      global_accuracy: 75.0,
      daily_questions: 8,
      daily_correct: 6,
      daily_accuracy: 75.0,
      learning_time_minutes: 24,
    });

    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByText('Adept')).toBeInTheDocument();
    expect(screen.getAllByText('120').length).toBeGreaterThan(0);
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getAllByText('75%').length).toBeGreaterThan(0);
    expect(screen.getByText(/Topic Mastery/i)).toBeInTheDocument();
    expect(screen.getByText(/Redis Live Operations/i)).toBeInTheDocument();
  });

  it('shows fallback banner and cached totals when API fails', async () => {
    fetchUserStatsMock.mockRejectedValueOnce(new Error('boom'));
    fetchUserTopicBreakdownMock.mockRejectedValueOnce(new Error('boom'));
    fetchUserDailyTrendMock.mockRejectedValueOnce(new Error('boom'));
    fetchRedisOpsStatsMock.mockRejectedValueOnce(new Error('boom'));

    render(<MemoryRouter><Dashboard /></MemoryRouter>);

    expect(await screen.findByText(/Could not load live stats/i)).toBeInTheDocument();
    expect(screen.getByText('0m')).toBeInTheDocument();
    expect(screen.getAllByText('0%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});
