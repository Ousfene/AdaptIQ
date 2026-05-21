/**
 * E2E Test: Timer Functionality
 *
 * Tests the quiz timer including:
 * - Timer countdown display
 * - Warning animation when time is low
 * - Auto-submit on timeout
 * - Timeout counts as wrong answer
 */
import { expect, test } from '@playwright/test';
import {
  setupAuthenticatedUser,
  waitForQuestionLoad,
  getTimerValue,
  generateUniqueUser,
} from './test-helpers';

test.describe('Timer Functionality', () => {
  // Note: These tests use shorter timeouts for efficiency
  // In real app, timer is 30 seconds

  test('timer displays and counts down', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await page.route('**/api/rooms/classic/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'test-session',
          first_question: {
            id: 'q-1',
            text: 'Timer test question?',
            options: ['A', 'B', 'C', 'D'],
            topic: 'history',
            difficulty: 3,
          },
          session_stats: { questions_answered: 0, correct_count: 0 },
        }),
      });
    });

    await page.goto('/rooms/classic');
    await page.getByRole('button', { name: /History/i }).click();
    await waitForQuestionLoad(page);

    // Timer should be visible
    const timerElement = page.locator('.font-mono');
    await expect(timerElement).toBeVisible();

    // Get initial timer value
    const initialTime = await getTimerValue(page);
    expect(initialTime).toBeGreaterThan(0);
    expect(initialTime).toBeLessThanOrEqual(30); // Max timer is 30s

    // Wait 2 seconds
    await page.waitForTimeout(2000);

    // Timer should have decreased
    const laterTime = await getTimerValue(page);
    expect(laterTime).toBeLessThan(initialTime);
  });

  test('timer shows warning animation when low', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await page.addInitScript(() => {
      sessionStorage.setItem('adaptiq_dev_mode', JSON.stringify({
        isEnabled: true,
        difficulty: 3,
        accuracy: 70,
        skipTimer: true,
      }));
    });

    await page.route('**/api/rooms/classic/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'test-session',
          first_question: {
            id: 'q-1',
            text: 'Timer warning test?',
            options: ['A', 'B', 'C', 'D'],
            topic: 'geography',
            difficulty: 3,
          },
          session_stats: { questions_answered: 0, correct_count: 0 },
        }),
      });
    });

    // Mock answer endpoint for timeout
    await page.route('**/api/rooms/classic/answer/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          correct: false,
          correct_index: 0,
          explanation: 'Time ran out!',
          theta_change: -0.2,
          session_ended: false,
          next_question: {
            id: 'q-2',
            text: 'Next question?',
            options: ['A', 'B', 'C', 'D'],
            topic: 'geography',
            difficulty: 3,
          },
          session_stats: { questions_answered: 1, correct_count: 0 },
        }),
      });
    });

    await page.goto('/rooms/classic?dev=true');
    await page.getByRole('button', { name: /Geography/i }).click();
    await waitForQuestionLoad(page);

    // Skip-timer dev mode should quickly force the timer to low/zero state.
    await page.waitForFunction(
      () => {
        const timer = document.querySelector('.font-mono');
        if (!timer) return false;
        const value = parseInt(timer.textContent?.replace('s', '') || '0', 10);
        return value <= 5;
      },
      { timeout: 10000 }
    );

    // Check for warning styling (red color and/or pulse animation)
    const timerElement = page.locator('.font-mono').first();
    const timerClasses = await timerElement.getAttribute('class');

    // Timer should have red color or pulse animation
    expect(
      timerClasses?.includes('text-red') || 
      timerClasses?.includes('animate-pulse')
    ).toBeTruthy();
  });

  test('auto-submits when timer reaches zero', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await page.addInitScript(() => {
      sessionStorage.setItem('adaptiq_dev_mode', JSON.stringify({
        isEnabled: true,
        difficulty: 3,
        accuracy: 70,
        skipTimer: true,
      }));
    });

    await page.route('**/api/rooms/classic/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'test-session',
          first_question: {
            id: 'q-timeout',
            text: 'Will timeout?',
            options: ['A', 'B', 'C', 'D'],
            topic: 'mix',
            difficulty: 3,
          },
          session_stats: { questions_answered: 0, correct_count: 0 },
        }),
      });
    });

    let answerSubmitted = false;
    await page.route('**/api/rooms/classic/answer/*', async (route) => {
      answerSubmitted = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          correct: false,
          correct_index: 0,
          explanation: 'Time ran out!',
          theta_change: -0.2,
          session_ended: true,
          next_question: null,
          session_stats: { questions_answered: 1, correct_count: 0 },
        }),
      });
    });

    await page.goto('/rooms/classic?dev=true');
    await page.getByRole('button', { name: /Mixed/i }).click();
    await waitForQuestionLoad(page);

    // Don't click anything - let timer run out
    // Wait for timer to reach 0
    await page.waitForFunction(
      () => {
        const timer = document.querySelector('.font-mono');
        if (!timer) return false;
        const value = parseInt(timer.textContent?.replace('s', '') || '0', 10);
        return value === 0;
      },
      { timeout: 10000 }
    );

    // Wait a moment for auto-submit to process
    await page.waitForTimeout(1000);

    // Verify answer was submitted automatically
    expect(answerSubmitted).toBeTruthy();

    // Explanation should appear (answer feedback)
    await expect(page.locator('text=Learn More')).toBeVisible({ timeout: 5000 });
  });

  test('timeout counts as wrong answer', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    await page.addInitScript(() => {
      sessionStorage.setItem('adaptiq_dev_mode', JSON.stringify({
        isEnabled: true,
        difficulty: 3,
        accuracy: 70,
        skipTimer: true,
      }));
    });

    await page.route('**/api/rooms/classic/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'test-session',
          first_question: {
            id: 'q-timeout-wrong',
            text: 'Timeout wrong test?',
            options: ['A', 'B', 'C', 'D'],
            topic: 'history',
            difficulty: 3,
          },
          session_stats: { questions_answered: 0, correct_count: 0 },
        }),
      });
    });

    let receivedAnswerIndex: number | null = null;
    await page.route('**/api/rooms/classic/answer/*', async (route) => {
      const postData = route.request().postDataJSON();
      receivedAnswerIndex = postData?.selected_index;
      
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          correct: false, // Timeout = wrong
          correct_index: 0,
          explanation: 'Time ran out!',
          theta_change: -0.2,
          session_ended: true,
          next_question: null,
          session_stats: { questions_answered: 1, correct_count: 0 },
        }),
      });
    });

    await page.goto('/rooms/classic?dev=true');
    await page.getByRole('button', { name: /History/i }).click();
    await waitForQuestionLoad(page);

    // Let timer run out
    await page.waitForFunction(
      () => {
        const timer = document.querySelector('.font-mono');
        if (!timer) return false;
        const value = parseInt(timer.textContent?.replace('s', '') || '0', 10);
        return value === 0;
      },
      { timeout: 10000 }
    );

    await page.waitForTimeout(1000);

    // Timeout should send -1 or null as answer index
    expect(receivedAnswerIndex).toBe(-1);

    // UI should show incorrect feedback
    const wrongIndicator = page.locator('text=Wrong').first();
    await expect(wrongIndicator).toBeVisible({ timeout: 3000 });
  });
});
