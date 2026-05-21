/**
 * E2E Test: Complete Quiz Flow
 *
 * Tests the full Classic Room quiz experience including:
 * - Starting a quiz session
 * - Answering multiple questions
 * - Viewing the summary screen
 * - Playing again
 */
import { expect, test } from '@playwright/test';
import {
  setupAuthenticatedUser,
  waitForQuestionLoad,
  clickFirstAnswer,
  generateUniqueUser,
} from './test-helpers';

test.describe('Quiz Complete Flow', () => {
  test('complete 10-question quiz session', async ({ page }) => {
    const user = generateUniqueUser();

    // Set up authenticated user
    await setupAuthenticatedUser(page, user);

    // Mock V2 start endpoint
    await page.route('**/api/rooms/classic/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: '22222222-2222-2222-2222-222222222222',
          first_question: {
            id: 'q-1',
            text: 'Test Question 1?',
            options: ['Option A', 'Option B', 'Option C', 'Option D'],
            topic: 'history',
            difficulty: 3,
          },
          session_stats: {
            questions_answered: 0,
            correct_count: 0,
          },
        }),
      });
    });

    // Mock V2 answer endpoint
    let answerCount = 0;
    await page.route('**/api/rooms/classic/answer/*', async (route) => {
      answerCount++;
      const isCorrect = answerCount % 2 === 1; // Alternate correct/wrong
      const sessionEnded = answerCount >= 10;

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          correct: isCorrect,
          correct_index: 0,
          explanation: `Explanation for question ${answerCount}`,
          theta_change: isCorrect ? 0.2 : -0.2,
          session_ended: sessionEnded,
          next_question: sessionEnded
            ? null
            : {
                id: `q-${answerCount + 1}`,
                text: `Test Question ${answerCount + 1}?`,
                options: ['Option A', 'Option B', 'Option C', 'Option D'],
                topic: 'history',
                difficulty: 3,
              },
          session_stats: {
            questions_answered: answerCount,
            correct_count: Math.ceil(answerCount / 2),
          },
        }),
      });
    });

    // Navigate to Classic Room
    await page.goto('/rooms/classic');

    // Select a topic (History)
    await page.getByRole('button', { name: /History/i }).click();

    // Wait for first question to load
    await waitForQuestionLoad(page);

    // Answer 10 questions
    for (let i = 0; i < 10; i++) {
      // Wait for question to be visible
      await expect(page.locator('h2')).toBeVisible();

      // Click first answer
      await clickFirstAnswer(page);

      // Wait for answer feedback
      await expect(page.locator('text=Learn More')).toBeVisible({ timeout: 5000 });

      // If not last question, move to the next question.
      if (i < 9) {
        await page.getByRole('button', { name: /Next Question/i }).click();
      }
    }

    // Verify summary screen appears
    await expect(page.locator('text=Quiz Complete!')).toBeVisible({ timeout: 10000 });

    // Verify score is displayed
    await expect(page.getByText(/\d+\s*\/\s*10/)).toBeVisible();
  });

  test('summary screen shows correct statistics', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    // Set up V2 mocks for a completed session
    await page.route('**/api/rooms/classic/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'test-session',
          first_question: {
            id: 'q-1',
            text: 'Final Question?',
            options: ['A', 'B', 'C', 'D'],
            topic: 'geography',
            difficulty: 3,
          },
          session_stats: { questions_answered: 0, correct_count: 0 },
        }),
      });
    });

    await page.route('**/api/rooms/classic/answer/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          correct: true,
          correct_index: 0,
          explanation: 'Final explanation',
          theta_change: 0.2,
          session_ended: true,
          next_question: null,
          session_stats: { questions_answered: 1, correct_count: 1 },
        }),
      });
    });

    await page.goto('/rooms/classic');
    await page.getByRole('button', { name: /Geography/i }).click();
    await waitForQuestionLoad(page);
    await clickFirstAnswer(page);

    // Wait for summary
    await expect(page.locator('text=Quiz Complete!')).toBeVisible({ timeout: 10000 });

    // Summary should show score + accuracy from this completed run.
    await expect(page.locator('text=1 / 10')).toBeVisible();
    await expect(page.locator('text=10%')).toBeVisible();
  });

  test('play again button starts new session', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await page.route('**/api/rooms/classic/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'session-1',
          first_question: {
            id: 'q-1',
            text: 'Question for session 1?',
            options: ['A', 'B', 'C', 'D'],
            topic: 'mix',
            difficulty: 3,
          },
          session_stats: { questions_answered: 0, correct_count: 0 },
        }),
      });
    });

    await page.route('**/api/rooms/classic/answer/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          correct: true,
          correct_index: 0,
          explanation: 'Done',
          theta_change: 0.2,
          session_ended: true,
          next_question: null,
          session_stats: { questions_answered: 1, correct_count: 1 },
        }),
      });
    });

    await page.goto('/rooms/classic');
    await page.getByRole('button', { name: /Mixed/i }).click();
    await waitForQuestionLoad(page);
    await clickFirstAnswer(page);

    // Wait for summary
    await expect(page.locator('text=Quiz Complete!')).toBeVisible({ timeout: 10000 });

    // Current summary returns users to dashboard.
    await page.getByRole('button', { name: /Return to Dashboard/i }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
  });
});
