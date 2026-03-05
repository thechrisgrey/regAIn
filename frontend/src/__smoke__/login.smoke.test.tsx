/**
 * Smoke: Login page
 *
 * Verifies the Login component renders correctly with:
 * - Sign in form (email, password, submit button)
 * - Brand panel / logo
 * - Toggle to sign up mode
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Login from '../components/Login';

vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
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
  })),
}));

vi.mock('../hooks/AuthContext', () => ({
  MfaRequiredError: class MfaRequiredError extends Error {
    constructor() {
      super('MFA verification required');
      this.name = 'MfaRequiredError';
    }
  },
}));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Login />
    </MemoryRouter>,
  );
}

describe('Smoke: Login', () => {
  it('renders without crashing', () => {
    // Confirms the login page mounts and renders a heading
    renderLogin();
    expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
  });

  it('displays the sign in form with email and password fields', () => {
    // Core form elements must exist for users to authenticate
    renderLogin();
    expect(screen.getByLabelText('Email')).toBeTruthy();
    expect(screen.getByLabelText('Password')).toBeTruthy();
  });

  it('renders the sign in submit button', () => {
    // Users need a way to submit credentials
    renderLogin();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy();
  });

  it('includes a link to switch to sign up mode', () => {
    // New users need a path to create an account
    renderLogin();
    expect(screen.getByText(/sign up/i)).toBeTruthy();
  });

  it('renders the Regain brand logo', () => {
    // Brand identity should be visible on the login page
    renderLogin();
    const logos = screen.getAllByAltText('Regain');
    expect(logos.length).toBeGreaterThanOrEqual(1);
  });

  it('heading shows "Sign in" by default', () => {
    // Confirms the default mode is sign in, not sign up
    renderLogin();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Sign in',
    );
  });
});
