import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import InternalLayout from '../components/InternalLayout';

const navigateMock = vi.fn();
const logoutMock = vi.fn();

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', username: 'tester', email: 'tester@example.com' },
    logout: logoutMock,
  }),
}));

vi.mock('react-router-dom', async () => {
  const mod = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...mod,
    useNavigate: () => navigateMock,
    useLocation: () => ({ pathname: '/dashboard' }),
  };
});

describe('InternalLayout button actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('navigates to dashboard and classic room, and logs out', async () => {
    render(
      <MemoryRouter>
        <InternalLayout><div>content</div></InternalLayout>
      </MemoryRouter>
    );

    await userEvent.click(screen.getByRole('button', { name: /Dashboard/i }));
    expect(navigateMock).toHaveBeenCalledWith('/dashboard');

    await userEvent.click(screen.getByRole('button', { name: /^Rooms/i }));
    await userEvent.click(screen.getByRole('button', { name: /^Rooms/i }));

    await userEvent.click(screen.getByRole('button', { name: /Classic Room/i }));
    expect(navigateMock).toHaveBeenCalledWith('/rooms/classic');

    const challengeBtn = screen.getByRole('button', { name: /Challenge Room/i });
    await userEvent.click(challengeBtn);
    expect(navigateMock).toHaveBeenCalledWith('/rooms/challenge');

    await userEvent.click(screen.getByRole('button', { name: /Logout/i }));
    expect(logoutMock).toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/');
  });
});
