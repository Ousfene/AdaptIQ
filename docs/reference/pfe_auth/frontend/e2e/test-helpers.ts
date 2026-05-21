/**
 * E2E Test Utilities
 *
 * Shared helper functions for Playwright tests.
 * Provides mocks for API endpoints and common test patterns.
 */
import { Page, Route } from '@playwright/test';

// Default test user credentials
export const DEFAULT_TEST_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'test@example.com',
  username: 'testuser',
  password: 'TestPass123!',
};

// Mock question data
export const MOCK_QUESTION = {
  id: '11111111-1111-1111-1111-111111111111',
  text: 'What is the capital of France?',
  options: ['Paris', 'London', 'Berlin', 'Madrid'],
  correctAnswer: 'Paris',
  difficulty: 3,
  explanation: 'Paris has been the capital of France since the 10th century.',
};

/**
 * Set up authentication state in localStorage
 */
export async function setupAuth(page: Page, user = DEFAULT_TEST_USER) {
  await page.addInitScript((userData) => {
    localStorage.setItem('adaptiq_token', 'mock-jwt-token');
    localStorage.setItem('adaptiq_user_id', userData.id);
  }, user);
}

/**
 * Mock the /api/auth/me endpoint
 */
export async function mockAuthMe(page: Page, user = DEFAULT_TEST_USER) {
  await page.route('**/api/auth/me', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: user.id,
        email: user.email,
        username: user.username,
      }),
    });
  });
}

/**
 * Mock the /api/auth/register endpoint
 */
export async function mockRegister(page: Page, user = DEFAULT_TEST_USER) {
  await page.route('**/api/auth/register', async (route: Route) => {
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'mock-jwt-token',
        token_type: 'bearer',
        user: {
          id: user.id,
          email: user.email,
          username: user.username,
        },
      }),
    });
  });
}

/**
 * Mock the /api/auth/login endpoint
 */
export async function mockLogin(page: Page, user = DEFAULT_TEST_USER) {
  await page.route('**/api/auth/login', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'mock-jwt-token',
        token_type: 'bearer',
        user: {
          id: user.id,
          email: user.email,
          username: user.username,
        },
      }),
    });
  });
}

/**
 * Mock the Classic Room questions endpoint
 */
export async function mockClassicQuestion(
  page: Page,
  question = MOCK_QUESTION,
  sessionId = '22222222-2222-2222-2222-222222222222'
) {
  await page.route('**/api/rooms/classic/start', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: sessionId,
        first_question: {
          id: question.id,
          text: question.text,
          options: question.options,
          topic: 'history',
          difficulty: question.difficulty,
        },
        session_stats: {
          questions_answered: 0,
          correct_count: 0,
        },
      }),
    });
  });
}

/**
 * Mock the Classic Room answers endpoint
 */
export async function mockClassicAnswer(
  page: Page,
  options: {
    correct?: boolean;
    sessionEnded?: boolean;
    nextQuestion?: typeof MOCK_QUESTION | null;
  } = {}
) {
  const { correct = true, sessionEnded = false, nextQuestion = null } = options;

  await page.route('**/api/rooms/classic/answer/*', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        correct,
        correct_index: 0,
        explanation: MOCK_QUESTION.explanation,
        theta_change: correct ? 0.2 : -0.2,
        session_ended: sessionEnded,
        next_question: nextQuestion
          ? {
              id: nextQuestion.id,
              text: nextQuestion.text,
              options: nextQuestion.options,
              topic: 'history',
              difficulty: nextQuestion.difficulty,
            }
          : null,
        session_stats: {
          questions_answered: 1,
          correct_count: correct ? 1 : 0,
        },
      }),
    });
  });
}

/**
 * Mock the Classic Room hints endpoint
 */
export async function mockClassicHint(page: Page, hintText = 'This city is known for the Eiffel Tower.') {
  await page.route('**/api/rooms/classic/hint/*', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        hint: hintText,
      }),
    });
  });
}

/**
 * Set up a fully authenticated user with all common mocks
 */
export async function setupAuthenticatedUser(page: Page, user = DEFAULT_TEST_USER) {
  await setupAuth(page, user);
  await mockAuthMe(page, user);
}

/**
 * Wait for the quiz question to be visible
 */
export async function waitForQuestionLoad(page: Page) {
  await page.locator('h2, .bg-red-50').first().waitFor({ state: 'visible' });
}

/**
 * Click the first answer option
 */
export async function clickFirstAnswer(page: Page) {
  const answerButton = page.locator('div.space-y-4 > button').first();
  await answerButton.click();
}

/**
 * Click a specific answer by text
 */
export async function clickAnswerByText(page: Page, answerText: string) {
  await page.locator('div.space-y-4 > button', { hasText: answerText }).click();
}

/**
 * Get the current timer value
 */
export async function getTimerValue(page: Page): Promise<number> {
  const timerText = await page.locator('.font-mono').textContent();
  return parseInt(timerText?.replace('s', '') || '0', 10);
}

/**
 * Wait for timer to reach a specific value
 */
export async function waitForTimer(page: Page, targetSeconds: number) {
  await page.waitForFunction(
    (target) => {
      const timer = document.querySelector('.font-mono');
      if (!timer) return false;
      const value = parseInt(timer.textContent?.replace('s', '') || '0', 10);
      return value <= target;
    },
    targetSeconds,
    { timeout: 35000 }
  );
}

/**
 * Check if the explanation section is visible
 */
export async function isExplanationVisible(page: Page): Promise<boolean> {
  return page.locator('text=Learn More').isVisible();
}

/**
 * Generate unique test data
 */
export function generateUniqueUser() {
  const id = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  return {
    id: `00000000-0000-0000-0000-${id.slice(-12).padStart(12, '0')}`,
    email: `e2e_${id}@example.com`,
    username: `e2e_${id}`,
    password: 'TestPass123!',
  };
}
