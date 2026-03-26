import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Layout from './Layout';

const mockGetToken = vi.fn().mockResolvedValue('mock-token');
const mockRefreshDashboard = vi.fn();

vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    user: { username: 'test-user' },
    signOut: vi.fn(),
    loading: false,
    getToken: mockGetToken,
  })),
}));

vi.mock('../services/api', () => ({
  cachedGet: vi.fn(),
  api: {
    profile: {
      recover: vi.fn().mockResolvedValue({ status: 'recovered' }),
    },
  },
}));

vi.mock('../hooks/useSharedData', () => ({
  useSharedData: vi.fn(() => ({
    dashboard: {
      data: null,
      loading: false,
      error: null,
    },
    refreshDashboard: mockRefreshDashboard,
  })),
}));

import { useSharedData } from '../hooks/useSharedData';
const mockedUseSharedData = vi.mocked(useSharedData);

function renderLayout() {
  return render(
    <MemoryRouter>
      <Layout />
    </MemoryRouter>,
  );
}

describe('Layout navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseSharedData.mockReturnValue({
      dashboard: { data: null, loading: false, error: null },
      refreshDashboard: mockRefreshDashboard,
    } as ReturnType<typeof useSharedData>);
  });

  it('includes Resume nav item between Evidence and Profile (Req 9.1)', () => {
    renderLayout();

    const nav = screen.getByRole('navigation');
    const links = Array.from(nav.querySelectorAll('a'));
    const labels = links.map(link => link.textContent?.trim());

    expect(labels).toContain('Resume');

    const evidenceIdx = labels.indexOf('Evidence');
    const resumeIdx = labels.indexOf('Resume');
    const profileIdx = labels.indexOf('Profile');

    expect(evidenceIdx).toBeLessThan(resumeIdx);
    expect(resumeIdx).toBeLessThan(profileIdx);
  });
});

describe('Recovery banner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not show banner when account is not deleted', () => {
    mockedUseSharedData.mockReturnValue({
      dashboard: {
        data: { campaign: null, stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: null } },
        loading: false,
        error: null,
      },
      refreshDashboard: mockRefreshDashboard,
    } as unknown as ReturnType<typeof useSharedData>);
    renderLayout();
    expect(screen.queryByText('Recover account')).not.toBeInTheDocument();
  });

  it('shows recovery banner when deletedAt is present', () => {
    mockedUseSharedData.mockReturnValue({
      dashboard: {
        data: {
          campaign: null,
          stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: null },
          deletedAt: '2026-03-26T12:00:00+00:00',
          deletionScheduledFor: '2026-04-25T12:00:00+00:00',
        },
        loading: false,
        error: null,
      },
      refreshDashboard: mockRefreshDashboard,
    } as unknown as ReturnType<typeof useSharedData>);
    renderLayout();
    expect(screen.getByText('Recover account')).toBeInTheDocument();
    expect(screen.getByText(/scheduled for deletion/)).toBeInTheDocument();
  });

  it('calls api.profile.recover when recover link is clicked', async () => {
    const { api: mockApi } = await import('../services/api');
    mockedUseSharedData.mockReturnValue({
      dashboard: {
        data: {
          campaign: null,
          stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: null },
          deletedAt: '2026-03-26T12:00:00+00:00',
          deletionScheduledFor: '2026-04-25T12:00:00+00:00',
        },
        loading: false,
        error: null,
      },
      refreshDashboard: mockRefreshDashboard,
    } as unknown as ReturnType<typeof useSharedData>);
    renderLayout();
    fireEvent.click(screen.getByText('Recover account'));
    await waitFor(() => {
      expect(mockApi.profile.recover).toHaveBeenCalledWith('mock-token');
    });
  });
});
