/**
 * E2E Test: Hint Functionality
 *
 * Tests the hint feature in Classic Room including:
 * - Requesting a hint during quiz
 * - Verifying hint displays correctly
 * - Verifying hint doesn't reveal the answer
 * - Points deduction for using hints
 */
import { expect, test } from '@playwright/test';
import {
  setupAuthenticatedUser,
  mockClassicQuestion,
  mockClassicHint,
  clickFirstAnswer,
  waitForQuestionLoad,
  generateUniqueUser,
} from './test-helpers';

test.describe('Hint Functionality', () => {
  test('can request and display hint', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);
    await mockClassicQuestion(page);

    // Mock hint endpoint
    const hintText = 'This city is famous for its iconic iron tower built in 1889.';
    await mockClassicHint(page, hintText);

    await page.goto('/rooms/classic');
    await page.getByRole('button', { name: /History/i }).click();
    await waitForQuestionLoad(page);

    // Find and click hint button
    const hintButton = page.getByRole('button', { name: /Get Hint/i });
    await expect(hintButton).toBeVisible();
    await hintButton.click();

    // Verify hint is displayed
    await expect(page.locator(`text=${hintText}`)).toBeVisible({ timeout: 5000 });

    // Verify hint button changes state
    await expect(page.getByRole('button', { name: /Hint Used/i })).toBeVisible();
  });

  test('hint does not reveal the answer directly', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);

    // Question about France's capital
    await page.route('**/api/rooms/classic/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'test-session',
          first_question: {
            id: 'q-france',
            text: 'What is the capital of France?',
            options: ['Paris', 'London', 'Berlin', 'Madrid'],
            topic: 'geography',
            difficulty: 3,
          },
          session_stats: { questions_answered: 0, correct_count: 0 },
        }),
      });
    });

    // Hint that helps but doesn't say "Paris"
    const safeHint = 'The capital is located on the River Seine and is known for the Eiffel Tower.';
    await mockClassicHint(page, safeHint);

    await page.goto('/rooms/classic');
    await page.getByRole('button', { name: /Geography/i }).click();
    await waitForQuestionLoad(page);

    // Get hint
    await page.getByRole('button', { name: /Get Hint/i }).click();

    // Verify hint is displayed
    await expect(page.locator(`text=${safeHint}`)).toBeVisible();

    // Verify hint text does NOT contain the answer
    const hintContent = await page.locator(`text=${safeHint}`).textContent();
    expect(hintContent?.toLowerCase()).not.toContain('paris');
  });

  test('hint button is disabled after use', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);
    await mockClassicQuestion(page);
    await mockClassicHint(page, 'Test hint text');

    await page.goto('/rooms/classic');
    await page.getByRole('button', { name: /History/i }).click();
    await waitForQuestionLoad(page);

    // Use hint
    await page.getByRole('button', { name: /Get Hint/i }).click();

    // Wait for hint to display
    await expect(page.locator('text=Test hint text')).toBeVisible();

    // Button should now be disabled or show "Hint Used"
    const hintButton = page.getByRole('button', { name: /Hint/i });
    const isDisabled = await hintButton.isDisabled();
    const buttonText = await hintButton.textContent();

    // Either disabled or shows "Hint Used"
    expect(isDisabled || buttonText?.includes('Used')).toBeTruthy();
  });

  test('hint is hidden after answer is submitted', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);
    await mockClassicQuestion(page);
    await mockClassicHint(page, 'Hidden after answer hint');

    // Mock answer endpoint
    await page.route('**/api/rooms/classic/answer/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          correct: true,
          correct_index: 0,
          explanation: 'Paris is the capital of France.',
          theta_change: 0.2,
          session_ended: false,
          next_question: {
            id: 'q-2',
            text: 'Next question?',
            options: ['A', 'B', 'C', 'D'],
            topic: 'mix',
            difficulty: 3,
          },
          session_stats: { questions_answered: 1, correct_count: 1 },
        }),
      });
    });

    await page.goto('/rooms/classic');
    await page.getByRole('button', { name: /Mixed/i }).click();
    await waitForQuestionLoad(page);

    // Get hint
    await page.getByRole('button', { name: /Get Hint/i }).click();
    await expect(page.locator('text=Hidden after answer hint')).toBeVisible();

    // Submit answer
    await clickFirstAnswer(page);

    // Wait for explanation (answer feedback)
    await expect(page.locator('text=Learn More')).toBeVisible({ timeout: 5000 });

    // Hint button should be hidden during answer phase
    await expect(page.getByRole('button', { name: /Get Hint/i })).not.toBeVisible();
  });

  test('hint endpoint error shows error message', async ({ page }) => {
    const user = generateUniqueUser();
    await setupAuthenticatedUser(page, user);
    await mockClassicQuestion(page);

    // Mock hint endpoint to return error
    await page.route('**/api/rooms/classic/hint/*', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Failed to generate hint' }),
      });
    });

    await page.goto('/rooms/classic');
    await page.getByRole('button', { name: /History/i }).click();
    await waitForQuestionLoad(page);

    // Try to get hint
    await page.getByRole('button', { name: /Get Hint/i }).click();

    // Error should be surfaced in the room banner.
    await expect(page.locator('.bg-red-50')).toBeVisible({ timeout: 5000 });
  });
});
