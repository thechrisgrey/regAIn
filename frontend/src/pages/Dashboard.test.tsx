import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';

const mockFetchDashboard = vi.fn();

vi.mock('../hooks/useDashboard', () => ({
  useDashboard: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    fetchDashboard: mockFetchDashboard,
  })),
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
      <Dashboard />
    </MemoryRouter>,
  );
}

describe('Dashboard', () => {
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
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
    expect(screen.queryByText('Unable to load dashboard')).not.toBeInTheDocument();
  });

  it('shows error state with retry button', () => {
    mockedUseDashboard.mockReturnValue({
      data: null,
      loading: false,
      error: 'Network error',
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Unable to load dashboard')).toBeInTheDocument();
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

  it('shows onboarding CTA when no campaign', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: null as unknown as typeof MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Get started')).toBeInTheDocument();
    expect(screen.getByText(/Set up your career campaign/)).toBeInTheDocument();
  });

  it('renders page heading with target role', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText(/Tracking your transition to ML Engineer/)).toBeInTheDocument();
  });

  it('renders campaign progress with stats', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Campaign Progress')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('missions completed')).toBeInTheDocument();
    expect(screen.getAllByText('8').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('evidence items')).toBeInTheDocument();
    expect(screen.getByText('days active')).toBeInTheDocument();
  });

  it('renders current focus section with target role', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Current Focus')).toBeInTheDocument();
    expect(screen.getAllByText('ML Engineer').length).toBeGreaterThanOrEqual(1);
  });

  it('renders Go to Missions link', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Go to Missions')).toBeInTheDocument();
  });

  it('renders skill focus list', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Skill Focus')).toBeInTheDocument();
    expect(screen.getAllByText('Python').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('TensorFlow').length).toBeGreaterThanOrEqual(1);
  });

  it('renders market position section', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    expect(screen.getByText('Market Position')).toBeInTheDocument();
    expect(screen.getByText('Explore missions')).toBeInTheDocument();
  });
});
