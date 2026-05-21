import { MemoryRouter } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, beforeEach, expect, it, vi } from 'vitest';

import Login from '../pages/Login';
import Signup from '../pages/Signup';
import ForgotPassword from '../pages/ForgotPassword';
import ResetPassword from '../pages/ResetPassword';

const loginMock = vi.fn().mockResolvedValue(undefined);
const signupMock = vi.fn().mockResolvedValue(undefined);

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    isLoading: false,
    login: loginMock,
    signup: signupMock,
    logout: vi.fn(),
  }),
}));

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const mod = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...mod,
    useNavigate: () => navigateMock,
    useLocation: () => ({ pathname: '/reset-password', state: { email: 'u@test.com' } }),
  };
});

describe('Auth pages button and link actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ message: 'ok' }),
    } as Response);
  });

  it('login page routes through forgot-password and signup links', async () => {
    render(<MemoryRouter><Login /></MemoryRouter>);

    await userEvent.click(screen.getByText('Forgot password?'));
    expect(navigateMock).toHaveBeenCalledWith('/forgot-password');

    await userEvent.click(screen.getByText('Sign up'));
    expect(navigateMock).toHaveBeenCalledWith('/signup');
  });

  it('signup page routes to login and triggers signup submit', async () => {
    render(<MemoryRouter><Signup /></MemoryRouter>);

    await userEvent.type(screen.getByPlaceholderText(/Username/i), 'tester');
    await userEvent.type(screen.getByPlaceholderText('Email'), 'tester@example.com');
    await userEvent.type(screen.getByPlaceholderText(/Password/i), 'Strong!123');
    await userEvent.click(screen.getByRole('button', { name: /^Sign Up$/i }));

    expect(signupMock).toHaveBeenCalled();

    await userEvent.click(screen.getByText('Log In'));
    expect(navigateMock).toHaveBeenCalledWith('/login');
  });

  it('forgot password page routes back to login', async () => {
    render(<MemoryRouter><ForgotPassword /></MemoryRouter>);

    await userEvent.click(screen.getByText('Back to Login'));
    expect(navigateMock).toHaveBeenCalledWith('/login');
  });

  it('reset password page routes to resend and back to login links', async () => {
    render(<MemoryRouter><ResetPassword /></MemoryRouter>);

    await userEvent.click(screen.getByText('Resend Code'));
    expect(navigateMock).toHaveBeenCalledWith('/forgot-password');

    await userEvent.click(screen.getByText('Back to Login'));
    expect(navigateMock).toHaveBeenCalledWith('/login');
  });
});
