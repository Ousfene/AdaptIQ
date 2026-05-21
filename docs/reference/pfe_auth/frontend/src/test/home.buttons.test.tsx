import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import Home from '../pages/Home';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const mod = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...mod,
    useNavigate: () => navigateMock,
  };
});

describe('Home page button actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('navigates to login and signup from CTAs', async () => {
    render(<MemoryRouter><Home /></MemoryRouter>);

    await userEvent.click(screen.getByRole('button', { name: /^Login$/i }));
    expect(navigateMock).toHaveBeenCalledWith('/login');

    await userEvent.click(screen.getByRole('button', { name: /Enroll Now/i }));
    expect(navigateMock).toHaveBeenCalledWith('/signup');

    await userEvent.click(screen.getByRole('button', { name: /Begin Your Pilgrimage/i }));
    expect(navigateMock).toHaveBeenCalledWith('/signup');
  });
});
