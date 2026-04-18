import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AnalyticsPage from '../AnalyticsPage';
import type { AnalyticsResponse } from '../../types';

// Mock hooks
const mockFetchAnalytics = vi.fn();
const mockSetPageSnapshot = vi.fn();

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => mockAnalyticsReturn,
}));

vi.mock('../../hooks/useMutationBus', () => ({
  useMutationBus: () => ({ setPageSnapshot: mockSetPageSnapshot }),
  useOnMutation: vi.fn(),
}));

const BASE_DATA: AnalyticsResponse = {
  skillBreakdown: [],
  activityHeatmap: [],
  velocityTrend: { weeks: [] },
  campaignEta: null,
  skillSuggestions: [],
  marketAlignment: null,
};

let mockAnalyticsReturn: {
  data: AnalyticsResponse | null;
  loading: boolean;
  error: string | null;
  fetchAnalytics: () => Promise<void>;
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AnalyticsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAnalyticsReturn = {
    data: null,
    loading: false,
    error: null,
    fetchAnalytics: mockFetchAnalytics,
  };
});

describe('MarketAlignmentCard', () => {
  it('shows empty state when marketAlignment is null', () => {
    mockAnalyticsReturn.data = { ...BASE_DATA, marketAlignment: null };
    renderPage();

    expect(screen.getByText('Market Alignment')).toBeInTheDocument();
    expect(screen.getByText(/Set a target role/)).toBeInTheDocument();
  });

  it('renders alignment score and target role', () => {
    mockAnalyticsReturn.data = {
      ...BASE_DATA,
      marketAlignment: {
        alignmentPct: 62.5,
        targetRole: 'AI QA Engineer',
        topGaps: [],
        topStrengths: [],
        calculatedAt: '2026-04-18T00:00:00Z',
      },
    };
    renderPage();

    expect(screen.getByText('63%')).toBeInTheDocument();
    expect(screen.getByText('AI QA Engineer')).toBeInTheDocument();
  });

  it('renders top gaps with demand percentages', () => {
    mockAnalyticsReturn.data = {
      ...BASE_DATA,
      marketAlignment: {
        alignmentPct: 40,
        targetRole: 'Data Scientist',
        topGaps: [
          { skill: 'Python Testing', gap: 0.78, demand: 78 },
          { skill: 'CI/CD', gap: 0.65, demand: 65 },
        ],
        topStrengths: [],
        calculatedAt: '2026-04-18T00:00:00Z',
      },
    };
    renderPage();

    expect(screen.getByText('Python Testing')).toBeInTheDocument();
    expect(screen.getByText('78% of postings')).toBeInTheDocument();
    expect(screen.getByText('CI/CD')).toBeInTheDocument();
    expect(screen.getByText('65% of postings')).toBeInTheDocument();
  });

  it('renders top strengths with scores', () => {
    mockAnalyticsReturn.data = {
      ...BASE_DATA,
      marketAlignment: {
        alignmentPct: 75,
        targetRole: 'QA Lead',
        topGaps: [],
        topStrengths: [
          { skill: 'Manual QA', userScore: 1.0 },
          { skill: 'Test Planning', userScore: 0.9 },
        ],
        calculatedAt: '2026-04-18T00:00:00Z',
      },
    };
    renderPage();

    expect(screen.getByText('Manual QA')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('Test Planning')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
  });
});
