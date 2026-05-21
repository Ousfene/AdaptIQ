import { expect, test } from '@playwright/test';

test('public auth route buttons navigate correctly', async ({ page }) => {
  await page.goto('/');

  await page.getByRole('button', { name: /^Login$/i }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByText('Forgot password?').click();
  await expect(page).toHaveURL(/\/forgot-password$/);

  await page.getByText('Back to Login').click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByText('Sign up').click();
  await expect(page).toHaveURL(/\/signup$/);

  await page.getByText('Log In').click();
  await expect(page).toHaveURL(/\/login$/);
});

test('protected routes redirect unauthenticated users to login', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/login$/);

  await page.goto('/rooms/classic');
  await expect(page).toHaveURL(/\/login$/);
});

test('authenticated users are redirected away from public auth routes', async ({ page }) => {
  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'u-1',
        email: 'u1@example.com',
        username: 'u1',
      }),
    });
  });

  await page.addInitScript(() => {
    localStorage.setItem('adaptiq_token', 'fake-token');
    localStorage.setItem('adaptiq_user_id', 'u-1');
  });

  await page.goto('/login');
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.goto('/signup');
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.goto('/forgot-password');
  await expect(page).toHaveURL(/\/dashboard$/);
});
