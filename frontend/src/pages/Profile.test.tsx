import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Profile from './Profile';

const mockFetchDashboard = vi.fn();
const mockGetToken = vi.fn().mockResolvedValue('mock-token');
const mockSignOut = vi.fn().mockResolvedValue(undefined);
const mockFetchEvidence = vi.fn();

vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    user: { username: 'jane.smith' },
    getToken: mockGetToken,
    signOut: mockSignOut,
  })),
}));

vi.mock('../hooks/useDashboard', () => ({
  useDashboard: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    fetchDashboard: mockFetchDashboard,
  })),
}));

vi.mock('../hooks/useEvidence', () => ({
  useEvidence: vi.fn(() => ({
    evidence: [],
    loading: false,
    error: null,
    fetchEvidence: mockFetchEvidence,
  })),
}));

vi.mock('../services/api', () => ({
  api: {
    profile: {
      delete: vi.fn().mockResolvedValue({ status: 'deleted' }),
    },
  },
}));

import { useDashboard } from '../hooks/useDashboard';
const mockedUseDashboard = vi.mocked(useDashboard);

const MOCK_CAMPAIGN = {
  userId: 'u1',
  campaignId: 'c1',
  title: 'Test Campaign',
  phase: 'foundation' as const,
  status: 'active' as const,
  startDate: '2025-01-01',
  targetRole: 'ML Engineer',
  skillsFocus: ['Python', 'TensorFlow'],
};

const MOCK_STATS = {
  missionsCompleted: 12,
  evidenceCount: 8,
  currentPhase: 'foundation' as const,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <Profile />
    </MemoryRouter>,
  );
}

describe('Profile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseDashboard.mockReturnValue({
      data: null,
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
  });

  it('shows skeleton when loading', () => {
    mockedUseDashboard.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.queryByText('Transition Profile')).not.toBeInTheDocument();
    expect(screen.queryByText('Unable to load profile')).not.toBeInTheDocument();
  });

  it('shows error state with retry button', () => {
    mockedUseDashboard.mockReturnValue({
      data: null,
      loading: false,
      error: 'Network error',
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Unable to load profile')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('retry button calls fetchDashboard', () => {
    mockedUseDashboard.mockReturnValue({
      data: null,
      loading: false,
      error: 'fail',
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(mockFetchDashboard).toHaveBeenCalled();
  });

  it('shows onboarding prompt when no campaign', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: null as unknown as typeof MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Complete onboarding to set up your profile.')).toBeInTheDocument();
    expect(screen.getByText('Delete account')).toBeInTheDocument();
  });

  it('renders identity summary with campaign data', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Transition Profile')).toBeInTheDocument();
    expect(screen.getAllByText('ML Engineer').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('jane.smith')).toBeInTheDocument();
    expect(screen.getAllByText('12').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('8').length).toBeGreaterThanOrEqual(1);
  });

  it('renders skills in focus', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Skills in Focus')).toBeInTheDocument();
    expect(screen.getAllByText('Python').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('TensorFlow').length).toBeGreaterThanOrEqual(1);
  });

  it('renders campaign journey section', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Campaign Journey')).toBeInTheDocument();
    expect(screen.getByText('View full campaign details')).toBeInTheDocument();
  });

  it('renders delete account section', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Delete account')).toBeInTheDocument();
    expect(screen.getByText('Delete my account')).toBeInTheDocument();
  });

  it('shows delete confirmation input when clicking delete', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    expect(screen.getByText('Type DELETE to confirm')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('continue button advances to step 2 after typing DELETE', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Delete now')).toBeInTheDocument();
    expect(screen.getByText('Schedule for later')).toBeInTheDocument();
    expect(screen.queryByText('Type DELETE to confirm')).not.toBeInTheDocument();
  });

  it('delete now calls api.profile.delete with immediate mode', async () => {
    const { api: mockApi } = await import('../services/api');
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByText('Delete now'));
    await waitFor(() => {
      expect(mockApi.profile.delete).toHaveBeenCalledWith('mock-token', 'immediate');
    });
  });

  it('schedule for later calls api.profile.delete with scheduled mode', async () => {
    const { api: mockApi } = await import('../services/api');
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByText('Schedule for later'));
    await waitFor(() => {
      expect(mockApi.profile.delete).toHaveBeenCalledWith('mock-token', 'scheduled');
    });
  });

  it('cancel button hides delete confirmation from step 1', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    expect(screen.getByText('Type DELETE to confirm')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByText('Type DELETE to confirm')).not.toBeInTheDocument();
  });

  it('cancel button resets from step 2 back to initial state', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Delete now')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByText('Delete now')).not.toBeInTheDocument();
    expect(screen.getByText('Delete my account')).toBeInTheDocument();
  });
});
