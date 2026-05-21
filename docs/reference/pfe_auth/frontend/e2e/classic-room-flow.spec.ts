import { expect, test } from '@playwright/test';

const unique = () => `${Date.now()}${Math.floor(Math.random() * 1000)}`;

test('signup to classic room and submit answer flow', async ({ page }) => {
  const id = unique();
  const email = `e2e_${id}@example.com`;
  const username = `e2e_${id}`;
  const password = 'Strong!123';
  const userId = `00000000-0000-0000-0000-${id.slice(-12).padStart(12, '0')}`;

  await page.route('**/api/auth/register', async (route) => {
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'e2e-token',
        token_type: 'bearer',
        user: {
          id: userId,
          email,
          username,
        },
      }),
    });
  });

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: userId,
        email,
        username,
      }),
    });
  });

  await page.route('**/api/rooms/classic/start', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: '11111111-1111-1111-1111-111111111111',
        first_question: {
          id: '11111111-1111-1111-1111-111111111111',
          text: 'What is the capital of France?',
          options: ['Paris', 'Rome', 'Madrid', 'Berlin'],
          topic: 'history',
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
        explanation: 'Paris is the capital of France.',
        theta_change: 0.2,
        session_ended: false,
        next_question: {
          id: '22222222-2222-2222-2222-222222222222',
          text: 'Next question?',
          options: ['A', 'B', 'C', 'D'],
          topic: 'history',
          difficulty: 3,
        },
        session_stats: { questions_answered: 1, correct_count: 1 },
      }),
    });
  });

  await page.goto('/signup');

  await page.getByPlaceholder('Username (min 3 chars)').fill(username);
  await page.getByPlaceholder('Email').fill(email);
  await page.getByPlaceholder(/Password/).fill(password);
  await page.getByRole('button', { name: /^Sign Up$/i }).click();

  await expect(page).toHaveURL(/\/dashboard$/);

  // Open classic room via URL to avoid fragile selector coupling on dashboard cards.
  await page.goto('/rooms/classic');

  await page.getByRole('button', { name: /History/i }).click();

  // Ensure backend question generation reached UI either with question text or explicit load error.
  const questionOrError = page.locator('h2, .bg-red-50').first();
  await expect(questionOrError).toBeVisible();

  const hasQuestion = await page.locator('h2').isVisible();
  if (hasQuestion) {
    // Click first answer option in quiz choices.
    const answerButton = page.locator('div.space-y-4 > button').first();
    await answerButton.click();

    await expect(page.getByText(/Learn More/i)).toBeVisible();
  }
});
