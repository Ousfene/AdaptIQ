/**
 * E2E Test: Profile Stats
 *
 * Tests the user profile page including:
 * - Stats display (total questions, accuracy, etc.)
 * - Concept mastery visualization
 * - Correct color coding for mastery levels
 */
import { expect, test, type Page } from '@playwright/test';
import { setupAuthenticatedUser, generateUniqueUser } from './test-helpers';

const makeStats = (overrides: Record<string, unknown> = {}) => ({
  id: 'profile-user-id',
  points: 1500,
  level: 'Scholar',
  total_questions: 120,
  correct_questions: 90,
  global_accuracy: 75,
  daily_questions: 10,
  daily_correct: 8,
  daily_accuracy: 80,
  learning_time_minutes: 35,
  ...overrides,
});

const makeConcepts = (overrides: Record<string, unknown> = {}) => ({
  concepts: {
    History: [
      {
        concept: 'Roman Empire',
        theta: 1.8,
        level: 'Advanced',
        responses: 24,
        lastUpdated: new Date().toISOString(),
      },
    ],
  },
  ...overrides,
});

const makeChallengeStatus = (overrides: Record<string, unknown> = {}) => ({
  current_rank: {
    id: 2,
    name: 'Silver',
    n_options: 4,
    has_timer: true,
    timer_seconds: 30,
  },
  can_skip_up: false,
  skip_attempts_remaining: 0,
  wins: 7,
  losses: 3,
  classic_games_played: 20,
  ...overrides,
});

async function mockProfileApis(
  page: Page,
  {
    stats = makeStats(),
    concepts = makeConcepts(),
    challenge = makeChallengeStatus(),
  }: {
    stats?: Record<string, unknown>;
    concepts?: Record<string, unknown>;
    challenge?: Record<string, unknown>;
  } = {},
) {
  await page.route('**/api/auth/stats', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(stats),
    });
  });

  await page.route('**/api/auth/stats/concept-mastery', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(concepts),
    });
  });

  await page.route('**/api/rooms/challenge/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(challenge),
    });
  });
}

test.describe('Profile Stats', () => {
  test('displays user profile information', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    const statsId = `profile-${user.username}`;
    await mockProfileApis(page, {
      stats: makeStats({ id: statsId, level: 'Scholar' }),
    });

    await page.goto('/profile');

    await expect(page.getByRole('heading', { name: statsId })).toBeVisible();
    await expect(page.locator('main').getByText('Scholar', { exact: true }).first()).toBeVisible();
  });

  test('displays quiz statistics', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await mockProfileApis(page, {
      stats: makeStats({
        points: 2500,
        level: 'Expert',
        total_questions: 150,
        correct_questions: 120,
        global_accuracy: 80,
      }),
    });

    await page.goto('/profile');

    await expect(page.locator('text=2500').first()).toBeVisible();
    await expect(page.locator('main').getByText('Expert', { exact: true }).first()).toBeVisible();
  });

  test('displays concept mastery section', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await mockProfileApis(page, {
      concepts: {
        concepts: {
          History: [
            {
              concept: 'Egyptian Empire',
              theta: 2.0,
              level: 'Advanced',
              responses: 50,
              lastUpdated: new Date().toISOString(),
            },
          ],
          Geography: [
            {
              concept: 'Amazon River Basin',
              theta: 0.5,
              level: 'Intermediate',
              responses: 20,
              lastUpdated: new Date().toISOString(),
            },
          ],
        },
      },
    });

    await page.goto('/profile');

    await expect(page.locator('text=Concept Mastery')).toBeVisible();
    await expect(page.locator('text=Egyptian Empire')).toBeVisible();
    await expect(page.locator('text=Amazon River Basin')).toBeVisible();
  });

  test('mastery levels have correct color coding', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await mockProfileApis(page, {
      concepts: {
        concepts: {
          History: [
            {
              concept: 'High Mastery',
              theta: 2.5,
              level: 'Advanced',
              responses: 10,
              lastUpdated: new Date().toISOString(),
            },
            {
              concept: 'Medium Mastery',
              theta: 0.5,
              level: 'Intermediate',
              responses: 8,
              lastUpdated: new Date().toISOString(),
            },
            {
              concept: 'Low Mastery',
              theta: -1.5,
              level: 'Beginner',
              responses: 6,
              lastUpdated: new Date().toISOString(),
            },
          ],
        },
      },
    });

    await page.goto('/profile');

    await expect(page.locator('.bg-green-500').first()).toBeVisible();
    await expect(page.locator('.bg-yellow-500').first()).toBeVisible();
    await expect(page.locator('.bg-red-500').first()).toBeVisible();
  });

  test('profile page handles empty stats gracefully', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    const statsId = `new-${user.username}`;
    await mockProfileApis(page, {
      stats: makeStats({
        id: statsId,
        points: 0,
        level: 'Novice',
        total_questions: 0,
        correct_questions: 0,
        global_accuracy: 0,
        daily_questions: 0,
        daily_correct: 0,
        daily_accuracy: 0,
      }),
      concepts: {
        concepts: {},
      },
    });

    await page.goto('/profile');

    await expect(page.getByRole('heading', { name: statsId })).toBeVisible();
    await expect(page.locator('text=Novice')).toBeVisible();
    await expect(page.locator('text=No concepts tracked yet')).toBeVisible();
  });

  test('profile shows theta value appropriately', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await mockProfileApis(page, {
      stats: makeStats({
        id: `theta-${user.username}`,
        points: 800,
        level: 'Intermediate',
      }),
      concepts: {
        concepts: {
          History: [
            {
              concept: 'Theta Test Concept',
              theta: 1.2,
              level: 'Advanced',
              responses: 12,
              lastUpdated: new Date().toISOString(),
            },
          ],
        },
      },
    });

    await page.goto('/profile');

    await expect(page.locator('text=Theta Test Concept')).toBeVisible();
    await expect(page.locator('text=Θ = 1.20')).toBeVisible();
  });
});
