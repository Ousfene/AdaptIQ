import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  fetchRedisOpsStats,
  fetchUserDailyTrend,
  fetchUserStats,
  fetchUserTopicBreakdown,
  generateQuestion,
  submitAnswer,
} from '../services/apiService';

describe('apiService contract behavior', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem('adaptiq_token', 'token123');
    localStorage.setItem('adaptiq_user_id', 'user-1');
  });

  it('generateQuestion sends clamped difficulty and auth header', async () => {
    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 'q1',
        text: 'Q?',
        options: ['A', 'B'],
        correctAnswer: 'A',
        explanation: 'E',
      }),
    } as Response);

    await generateQuestion('History', 99);

    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(String(init?.body));
    expect(body.difficulty).toBe(5);
    expect(body.user_id).toBe('user-1');
    expect(body.session_id).toBeTypeOf('string');
    expect((init?.headers as Record<string, string>).Authorization).toContain('Bearer ');
  });

  it('submitAnswer returns safe fallback when API fails', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: false,
      status: 500,
    } as Response);

    const result = await submitAnswer({
      question_id: 'q1',
      selected_answer: 'A',
      time_taken: 5,
      used_hint: false,
    });

    expect(result.success).toBe(false);
    expect(result.updated_difficulty).toBe(2);
  });

  it('fetchUserStats throws on non-ok response', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Unauthorized' }),
    } as Response);

    await expect(fetchUserStats()).rejects.toThrow('Unauthorized');
  });

  it('fetchUserDailyTrend clamps days query parameter', async () => {
    const fetchMock = vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ days: 90, points: [] }),
    } as Response);

    await fetchUserDailyTrend(999);

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('days=90');
  });

  it('fetchUserTopicBreakdown returns payload on success', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        topics: [
          {
            topic: 'History',
            total_questions: 4,
            correct_questions: 3,
            accuracy: 75,
            hints_used: 1,
            avg_time_seconds: 8.5,
          },
        ],
      }),
    } as Response);

    const payload = await fetchUserTopicBreakdown();
    expect(payload.topics.length).toBeGreaterThan(0);
    expect(payload.topics[0].topic).toBe('History');
  });

  it('fetchRedisOpsStats throws on non-ok response', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'Redis metrics unavailable' }),
    } as Response);

    await expect(fetchRedisOpsStats()).rejects.toThrow('Redis metrics unavailable');
  });
});
