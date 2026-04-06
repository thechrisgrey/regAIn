/**
 * Smoke: Layout component
 *
 * Verifies the main application Layout renders correctly with
 * sidebar navigation, all 10 nav items, sign-out button, and
 * the main content area with ErrorBoundary + Suspense.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Layout from '../components/Layout';

// Mock useAuth -- Layout calls useAuth() for user, signOut, getToken
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    user: { userId: 'smoke-user-id', username: 'smoke@example.com' },
    loading: false,
    mfaPending: false,
    signIn: vi.fn(),
    confirmMfa: vi.fn(),
    signUp: vi.fn(),
    confirmSignUp: vi.fn(),
    resendConfirmationCode: vi.fn(),
    signOut: vi.fn(),
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

// Mock api and cachedGet -- Layout imports both for prefetch and recovery
vi.mock('../services/api', () => ({
  cachedGet: vi.fn(),
  api: {
    profile: {
      recover: vi.fn().mockResolvedValue({ status: 'recovered' }),
    },
  },
}));

// Mock useSharedData -- RecoveryBanner uses it to check for deletedAt
vi.mock('../hooks/useSharedData', () => ({
  useSharedData: vi.fn(() => ({
    dashboard: { data: null, loading: false, error: null },
    refreshDashboard: vi.fn(),
  })),
}));

// Mock CoachModal -- depends on CoachingContext
vi.mock('../components/CoachModal', () => ({
  default: () => null,
}));

// Mock ConnectionBanner -- depends on NetworkStatusContext
vi.mock('../components/ConnectionBanner', () => ({
  default: () => null,
}));

// Mock useNetworkStatusHook -- imported by ConnectionBanner
vi.mock('../hooks/useNetworkStatusHook', () => ({
  useNetworkStatus: vi.fn(() => ({ isOnline: true, isReconnecting: false })),
}));

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Layout />
    </MemoryRouter>,
  );
}

describe('Smoke: Layout', () => {
  it('renders without crashing', () => {
    // Confirms the Layout component mounts and produces visible output
    renderLayout();
    expect(document.body.querySelector('nav')).toBeTruthy();
    expect(document.body.querySelector('main')).toBeTruthy();
  });

  it('renders the sidebar navigation with all nav items', () => {
    // Verifies every expected navigation link is present in the sidebar
    // Coaching removed — replaced by persistent CoachModal
    renderLayout();

    const nav = screen.getByRole('navigation', { name: /main navigation/i });
    const links = within(nav).getAllByRole('link');
    const labels = links.map((link) => link.textContent?.trim());

    const expectedLabels = [
      'Dashboard',
      'Missions',
      'Voice Practice',
      'Evidence',
      'Scorecard',
      'Analytics',
      'Resume',
      'Careers',
      'Profile',
    ];

    for (const label of expectedLabels) {
      expect(labels).toContain(label);
    }
    expect(labels).not.toContain('Coaching');
  });

  it('renders the sign-out button', () => {
    // Confirms sign-out functionality is accessible to the user
    renderLayout();
    const signOutButton = screen.getByText('Sign out');
    expect(signOutButton).toBeTruthy();
    expect(signOutButton.tagName).toBe('BUTTON');
  });

  it('displays the current user email', () => {
    // Verifies the logged-in user identity is shown in the sidebar
    renderLayout();
    expect(screen.getByText('smoke@example.com')).toBeTruthy();
  });

  it('renders the Regain logo', () => {
    // Confirms the brand identity is visible
    renderLayout();
    const logos = screen.getAllByAltText('Regain');
    expect(logos.length).toBeGreaterThanOrEqual(1);
  });

  it('contains a main content area', () => {
    // Confirms the main content outlet container exists
    renderLayout();
    const main = document.querySelector('main');
    expect(main).toBeTruthy();
    expect(main!.className).toContain('flex-1');
  });

  it('renders the mobile hamburger menu button', () => {
    // Confirms the mobile navigation trigger exists for responsive design
    renderLayout();
    const menuButton = screen.getByLabelText('Open navigation');
    expect(menuButton).toBeTruthy();
  });

  it('nav links point to the correct routes', () => {
    // Verifies each link targets the expected URL path
    renderLayout();

    const nav = screen.getByRole('navigation', { name: /main navigation/i });
    const expectedRoutes: Record<string, string> = {
      Dashboard: '/dashboard',
      Missions: '/missions',
      'Voice Practice': '/voice-practice',
      Evidence: '/evidence',
      Scorecard: '/scorecard',
      Analytics: '/analytics',
      Resume: '/resume',
      Careers: '/onet',
      Profile: '/profile',
    };

    for (const [label, href] of Object.entries(expectedRoutes)) {
      const link = within(nav).getByText(label).closest('a');
      expect(link).toBeTruthy();
      expect(link!.getAttribute('href')).toBe(href);
    }
  });
});
