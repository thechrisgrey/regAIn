import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Missions from './Missions';

const mockFetchMissions = vi.fn();
const mockCompleteMission = vi.fn();
const mockGenerateMission = vi.fn();
const mockLoadMore = vi.fn();
const mockFetchDashboard = vi.fn();
const mockEmit = vi.fn();

vi.mock('../hooks/useMissions', () => ({
  useMissions: vi.fn(() => ({
    missions: [],
    dailyRemaining: null,
    dailyLimit: null,
    loading: false,
    error: null,
    fetchMissions: mockFetchMissions,
    completeMission: mockCompleteMission,
    generateMission: mockGenerateMission,
    nextCursor: null,
    loadMore: mockLoadMore,
  })),
}));

vi.mock('../hooks/useDashboard', () => ({
  useDashboard: vi.fn(() => ({
    data: {
      campaign: {
        userId: 'u1',
        campaignId: 'c1',
        title: 'T',
        phase: 'foundation',
        status: 'active',
        startDate: '2025-01-01',
        targetRole: 'Engineer',
        skillsFocus: [],
      },
    },
    loading: false,
    fetchDashboard: mockFetchDashboard,
  })),
}));

vi.mock('../hooks/useMutationBus', () => ({
  useMutationBus: vi.fn(() => ({ emit: mockEmit })),
}));

vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

vi.mock('../services/api', () => ({
  api: {
    evidence: {
      suggestTags: vi.fn().mockResolvedValue({ suggestions: [] }),
    },
  },
}));

vi.mock('../components/ui', async () => {
  const actual = await vi.importActual('../components/ui');
  return {
    ...actual,
    useToast: vi.fn(() => ({ toast: vi.fn() })),
  };
});

import { useMissions } from '../hooks/useMissions';
import { useDashboard } from '../hooks/useDashboard';
const mockedUseMissions = vi.mocked(useMissions);
const mockedUseDashboard = vi.mocked(useDashboard);

const MOCK_MISSION_ACTIVE = {
  userId: 'u1',
  missionId: 'm1',
  campaignId: 'c1',
  title: 'Write a Python script',
  description: 'Create a data processing pipeline',
  status: 'pending' as const,
};

const MOCK_MISSION_ACTIVE_2 = {
  userId: 'u1',
  missionId: 'm2',
  campaignId: 'c1',
  title: 'Build API endpoint',
  description: 'REST API for user data',
  status: 'pending' as const,
};

const MOCK_MISSION_COMPLETED = {
  userId: 'u1',
  missionId: 'm3',
  campaignId: 'c1',
  title: 'Completed mission one',
  description: 'Already done',
  status: 'completed' as const,
  completedDate: '2025-06-15',
};

const MOCK_MISSION_SKIPPED = {
  userId: 'u1',
  missionId: 'm4',
  campaignId: 'c1',
  title: 'Skipped mission',
  description: 'Was skipped',
  status: 'skipped' as const,
  completedDate: '2025-06-14',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <Missions />
    </MemoryRouter>,
  );
}

describe('Missions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseMissions.mockReturnValue({
      missions: [],
      dailyRemaining: null,
      dailyLimit: null,
      loading: false,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    mockedUseDashboard.mockReturnValue({
      data: {
        campaign: {
          userId: 'u1',
          campaignId: 'c1',
          title: 'T',
          phase: 'foundation' as const,
          status: 'active' as const,
          startDate: '2025-01-01',
          targetRole: 'Engineer',
          skillsFocus: [],
        },
        stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: 'foundation' as const },
      },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
  });

  it('shows skeleton when loading with no missions', () => {
    mockedUseMissions.mockReturnValue({
      missions: [],
      dailyRemaining: null,
      dailyLimit: null,
      loading: true,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    mockedUseDashboard.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.queryByText('Missions')).not.toBeInTheDocument();
    expect(screen.queryByText('Unable to load missions')).not.toBeInTheDocument();
  });

  it('shows error state with retry', () => {
    mockedUseMissions.mockReturnValue({
      missions: [],
      dailyRemaining: null,
      dailyLimit: null,
      loading: false,
      error: 'Service unavailable',
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    renderPage();
    expect(screen.getByText('Unable to load missions')).toBeInTheDocument();
    expect(screen.getByText('Service unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows onboarding CTA when no campaign', () => {
    mockedUseDashboard.mockReturnValue({
      data: {
        campaign: null as unknown as import('../types').Campaign,
        stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: 'foundation' as const },
      },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Complete onboarding to unlock missions')).toBeInTheDocument();
    expect(screen.getByText('Go to Onboarding')).toBeInTheDocument();
  });

  it('renders primary mission card with active mission', () => {
    mockedUseMissions.mockReturnValue({
      missions: [MOCK_MISSION_ACTIVE],
      dailyRemaining: 5,
      dailyLimit: 6,
      loading: false,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    renderPage();
    expect(screen.getByText('Current Mission')).toBeInTheDocument();
    expect(screen.getByText('Write a Python script')).toBeInTheDocument();
    expect(screen.getByText('Create a data processing pipeline')).toBeInTheDocument();
  });

  it('renders alternate missions when multiple active', () => {
    mockedUseMissions.mockReturnValue({
      missions: [MOCK_MISSION_ACTIVE, MOCK_MISSION_ACTIVE_2],
      dailyRemaining: 5,
      dailyLimit: 6,
      loading: false,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    renderPage();
    expect(screen.getByText('Alternate Missions')).toBeInTheDocument();
    expect(screen.getByText('Build API endpoint')).toBeInTheDocument();
  });

  it('shows all caught up with generate button when no active missions', () => {
    mockedUseMissions.mockReturnValue({
      missions: [MOCK_MISSION_COMPLETED],
      dailyRemaining: 4,
      dailyLimit: 6,
      loading: false,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    renderPage();
    expect(screen.getByText('All caught up')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Generate New Mission' })).toBeInTheDocument();
    expect(screen.getByText(/4 of 6 remaining today/)).toBeInTheDocument();
  });

  it('shows daily limit reached message', () => {
    mockedUseMissions.mockReturnValue({
      missions: [MOCK_MISSION_COMPLETED],
      dailyRemaining: 0,
      dailyLimit: 6,
      loading: false,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    renderPage();
    expect(screen.getByText('All caught up')).toBeInTheDocument();
    expect(screen.getByText(/reached today's mission limit/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Generate New Mission' })).not.toBeInTheDocument();
  });

  it('renders mission history with completed badge', () => {
    mockedUseMissions.mockReturnValue({
      missions: [MOCK_MISSION_COMPLETED],
      dailyRemaining: null,
      dailyLimit: null,
      loading: false,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    renderPage();
    expect(screen.getByText('Mission History')).toBeInTheDocument();
    expect(screen.getByText('Completed mission one')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('renders skipped badge for skipped missions', () => {
    mockedUseMissions.mockReturnValue({
      missions: [MOCK_MISSION_SKIPPED],
      dailyRemaining: null,
      dailyLimit: null,
      loading: false,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    renderPage();
    expect(screen.getByText('Skipped mission')).toBeInTheDocument();
    expect(screen.getByText('Skipped')).toBeInTheDocument();
  });

  it('shows empty history message', () => {
    renderPage();
    expect(screen.getByText('Mission History')).toBeInTheDocument();
    expect(screen.getByText(/Your mission history will appear here/)).toBeInTheDocument();
  });

  it('shows active mission count in subtitle', () => {
    mockedUseMissions.mockReturnValue({
      missions: [MOCK_MISSION_ACTIVE, MOCK_MISSION_ACTIVE_2],
      dailyRemaining: 5,
      dailyLimit: 6,
      loading: false,
      error: null,
      fetchMissions: mockFetchMissions,
      completeMission: mockCompleteMission,
      generateMission: mockGenerateMission,
      nextCursor: null,
      loadMore: mockLoadMore,
    });
    renderPage();
    expect(screen.getByText('2 active missions available')).toBeInTheDocument();
  });
});
