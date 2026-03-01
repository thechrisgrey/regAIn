import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import * as fc from 'fast-check';
import { ProtectedRoute } from './ProtectedRoute';

/**
 * Property 11: Protected Route Authentication
 *
 * For any protected route in the React application, when accessed without
 * authentication, it should redirect the user to the login page.
 *
 * Validates: Requirements 7.5
 */

// Mock useAuth hook to control auth state
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../hooks/useAuth';

const mockedUseAuth = vi.mocked(useAuth);

// Arbitrary for generating route path segments (valid URL path characters)
const pathSegmentArb = fc
  .array(
    fc.constantFrom(
      ...'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'.split('')
    ),
    { minLength: 1, maxLength: 20 }
  )
  .map((chars) => chars.join(''));

const routePathArb = fc
  .array(pathSegmentArb, { minLength: 1, maxLength: 5 })
  .map((segments) => '/' + segments.join('/'));

// Arbitrary for generating child content text
const childContentArb = fc
  .array(
    fc.constantFrom(
      ...'abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('')
    ),
    { minLength: 1, maxLength: 50 }
  )
  .map((chars) => chars.join(''));

describe('Property 11: Protected Route Authentication', () => {
  /**
   * **Validates: Requirements 7.5**
   *
   * For any route path, when user is not authenticated (user is null),
   * ProtectedRoute should redirect to /login via Navigate component.
   */
  it('redirects unauthenticated users to /login for any protected route', () => {
    fc.assert(
      fc.property(routePathArb, childContentArb, (routePath, childText) => {
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
        });

        const { unmount } = render(
          <MemoryRouter initialEntries={[routePath]}>
            <ProtectedRoute>
              <div data-testid="protected-content">{childText}</div>
            </ProtectedRoute>
          </MemoryRouter>
        );

        // Child content should NOT be rendered
        expect(screen.queryByTestId('protected-content')).toBeNull();

        unmount();
      }),
      { numRuns: 150 }
    );
  });

  /**
   * **Validates: Requirements 7.5**
   *
   * For any route path, when user IS authenticated,
   * ProtectedRoute should render the child content.
   */
  it('renders children for authenticated users on any route', () => {
    fc.assert(
      fc.property(routePathArb, childContentArb, (routePath, childText) => {
        mockedUseAuth.mockReturnValue({
          user: { userId: 'user-123', username: 'test@example.com' },
          loading: false,
          mfaPending: false,
          signIn: vi.fn(),
          confirmMfa: vi.fn(),
          signUp: vi.fn(),
          confirmSignUp: vi.fn(),
          resendConfirmationCode: vi.fn(),
          signOut: vi.fn(),
          getToken: vi.fn(),
        });

        const { unmount } = render(
          <MemoryRouter initialEntries={[routePath]}>
            <ProtectedRoute>
              <div data-testid="protected-content">{childText}</div>
            </ProtectedRoute>
          </MemoryRouter>
        );

        // Child content SHOULD be rendered
        const content = screen.getByTestId('protected-content');
        expect(content).toBeTruthy();
        expect(content.textContent).toBe(childText);

        unmount();
      }),
      { numRuns: 150 }
    );
  });

  /**
   * **Validates: Requirements 7.5**
   *
   * While loading, ProtectedRoute should show loading state
   * and not render children or redirect.
   */
  it('shows loading state while auth is being checked', () => {
    fc.assert(
      fc.property(routePathArb, childContentArb, (routePath, childText) => {
        mockedUseAuth.mockReturnValue({
          user: null,
          loading: true,
          mfaPending: false,
          signIn: vi.fn(),
          confirmMfa: vi.fn(),
          signUp: vi.fn(),
          confirmSignUp: vi.fn(),
          resendConfirmationCode: vi.fn(),
          signOut: vi.fn(),
          getToken: vi.fn(),
        });

        const { unmount } = render(
          <MemoryRouter initialEntries={[routePath]}>
            <ProtectedRoute>
              <div data-testid="protected-content">{childText}</div>
            </ProtectedRoute>
          </MemoryRouter>
        );

        // Child content should NOT be rendered during loading
        expect(screen.queryByTestId('protected-content')).toBeNull();
        // Loading text should be visible
        expect(screen.getByText('Loading...')).toBeTruthy();

        unmount();
      }),
      { numRuns: 150 }
    );
  });
});
