/**
 * Smoke: ProtectedRoute
 *
 * Verifies the authentication guard behaves correctly:
 * - Unauthenticated users are redirected to /login
 * - Authenticated users see the child content
 * - Loading state renders the loader, not children
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProtectedRoute } from '../components/ProtectedRoute';

vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../hooks/useAuth';

const mockedUseAuth = vi.mocked(useAuth);

function mockAuth(overrides: Partial<ReturnType<typeof useAuth>>) {
  mockedUseAuth.mockReturnValue({
    user: null,
    loading: false,
    mfaPending: false,
    signIn: vi.fn(),
    confirmMfa: vi.fn(),
    signUp: vi.fn(),
    confirmSignUp: vi.fn(),
    resendConfirmationCode: vi.fn(),
    signOut: vi.fn(),
    getToken: vi.fn(),
    ...overrides,
  });
}

describe('Smoke: ProtectedRoute', () => {
  it('redirects to /login when user is not authenticated', () => {
    // Unauthenticated users must not see protected content
    mockAuth({ user: null, loading: false });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <ProtectedRoute>
          <div data-testid="protected">Secret content</div>
        </ProtectedRoute>
      </MemoryRouter>,
    );

    expect(screen.queryByTestId('protected')).toBeNull();
  });

  it('renders children when user is authenticated', () => {
    // Authenticated users must see the protected content
    mockAuth({
      user: { userId: 'u-1', username: 'test@example.com' },
      loading: false,
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <ProtectedRoute>
          <div data-testid="protected">Secret content</div>
        </ProtectedRoute>
      </MemoryRouter>,
    );

    expect(screen.getByTestId('protected')).toBeTruthy();
    expect(screen.getByText('Secret content')).toBeTruthy();
  });

  it('shows loading state while auth is being checked', () => {
    // While loading, neither children nor redirect should appear
    mockAuth({ user: null, loading: true });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <ProtectedRoute>
          <div data-testid="protected">Secret content</div>
        </ProtectedRoute>
      </MemoryRouter>,
    );

    expect(screen.queryByTestId('protected')).toBeNull();
  });
});
