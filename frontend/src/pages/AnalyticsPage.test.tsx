import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import AnalyticsPage from './AnalyticsPage';

const mockFetchAnalytics = vi.fn();

vi.mock('../hooks/useAnalytics', () => ({
  useAnalytics: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    fetchAnalytics: mockFetchAnalytics,
  })),
}));

import { useAnalytics } from '../hooks/useAnalytics';
const mockedUseAnalytics = vi.mocked(useAnalytics);

const MOCK_ANALYTICS = {
  campaignEta: {
    estimatedDaysRemaining: 45,
    completionRate: 0.35,
    dailyRate: 1.2,
    confidence: 'medium' as const,
  },
  velocityTrend: {
    weeks: [
      { weekStart: '2025-06-02', weekEnd: '2025-06-08', completed: 4 },
      { weekStart: '2025-06-09', weekEnd: '2025-06-15', completed: 6 },
      { weekStart: '2025-06-16', weekEnd: '2025-06-22', completed: 3 },
    ],
  },
  activityHeatmap: [
    { date: '2025-06-01', count: 2 },
    { date: '2025-06-02', count: 0 },
    { date: '2025-06-03', count: 1 },
  ],
  skillBreakdown: [
    { skill: 'Python', count: 8, ratio: 0.4 },
    { skill: 'TensorFlow', count: 5, ratio: 0.25 },
    { skill: 'Data Analysis', count: 3, ratio: 0.15 },
  ],
  skillSuggestions: ['Docker', 'Kubernetes'],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockedUseAnalytics.mockReturnValue({
    data: null,
    loading: false,
    error: null,
    fetchAnalytics: mockFetchAnalytics,
  });
});

describe('AnalyticsPage', () => {
  it('shows heading in all states', () => {
    render(<AnalyticsPage />);
    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.getByText('Career intelligence and progress tracking')).toBeInTheDocument();
  });

  it('shows skeleton when loading', () => {
    mockedUseAnalytics.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.queryByText('Campaign Estimate')).not.toBeInTheDocument();
  });

  it('shows error state with retry', () => {
    mockedUseAnalytics.mockReturnValue({
      data: null,
      loading: false,
      error: 'API unavailable',
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('Unable to load analytics')).toBeInTheDocument();
    expect(screen.getByText('API unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('renders campaign ETA with data', () => {
    mockedUseAnalytics.mockReturnValue({
      data: MOCK_ANALYTICS,
      loading: false,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('Campaign Estimate')).toBeInTheDocument();
    expect(screen.getByText('45d')).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();
    expect(screen.getByText('35%')).toBeInTheDocument();
    expect(screen.getByText('1.2')).toBeInTheDocument();
  });

  it('renders velocity chart', () => {
    mockedUseAnalytics.mockReturnValue({
      data: MOCK_ANALYTICS,
      loading: false,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('Weekly Velocity')).toBeInTheDocument();
  });

  it('renders activity heatmap', () => {
    mockedUseAnalytics.mockReturnValue({
      data: MOCK_ANALYTICS,
      loading: false,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('Activity (90 days)')).toBeInTheDocument();
  });

  it('renders skill breakdown bars', () => {
    mockedUseAnalytics.mockReturnValue({
      data: MOCK_ANALYTICS,
      loading: false,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('Skill Breakdown')).toBeInTheDocument();
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getByText('TensorFlow')).toBeInTheDocument();
    expect(screen.getByText('Data Analysis')).toBeInTheDocument();
  });

  it('renders skill gaps with suggestions', () => {
    mockedUseAnalytics.mockReturnValue({
      data: MOCK_ANALYTICS,
      loading: false,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('Skill Gaps')).toBeInTheDocument();
    expect(screen.getByText('Docker')).toBeInTheDocument();
    expect(screen.getByText('Kubernetes')).toBeInTheDocument();
    expect(screen.getByText(/2 campaign skills without evidence yet/)).toBeInTheDocument();
  });

  it('shows empty skill gaps message when no suggestions', () => {
    mockedUseAnalytics.mockReturnValue({
      data: { ...MOCK_ANALYTICS, skillSuggestions: [] },
      loading: false,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('All campaign skills have evidence. Keep building depth.')).toBeInTheDocument();
  });

  it('shows empty skill breakdown message when no skills', () => {
    mockedUseAnalytics.mockReturnValue({
      data: { ...MOCK_ANALYTICS, skillBreakdown: [] },
      loading: false,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('Complete missions and log evidence to see your skill distribution.')).toBeInTheDocument();
  });

  it('shows no campaign ETA message when eta is null', () => {
    mockedUseAnalytics.mockReturnValue({
      data: { ...MOCK_ANALYTICS, campaignEta: null },
      loading: false,
      error: null,
      fetchAnalytics: mockFetchAnalytics,
    });
    render(<AnalyticsPage />);
    expect(screen.getByText('No active campaign. Complete onboarding to see projected completion.')).toBeInTheDocument();
  });
});
