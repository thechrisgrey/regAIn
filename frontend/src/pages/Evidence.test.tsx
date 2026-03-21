import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Evidence from './Evidence';

const mockFetchEvidence = vi.fn();

vi.mock('../hooks/useEvidence', () => ({
  useEvidence: vi.fn(() => ({
    evidence: [],
    loading: false,
    error: null,
    fetchEvidence: mockFetchEvidence,
    nextCursor: null,
    loadMore: vi.fn(),
  })),
}));

import { useEvidence } from '../hooks/useEvidence';
const mockedUseEvidence = vi.mocked(useEvidence);

const MOCK_EVIDENCE = [
  {
    userId: 'u1',
    evidenceId: 'e1',
    missionId: 'm1',
    skillTag: 'Python',
    reflection: 'Built a data pipeline using pandas',
    createdAt: '2025-06-01T10:00:00Z',
  },
  {
    userId: 'u1',
    evidenceId: 'e2',
    missionId: 'm2',
    skillTag: 'Python',
    reflection: 'Created unit tests for API',
    createdAt: '2025-06-02T10:00:00Z',
  },
  {
    userId: 'u1',
    evidenceId: 'e3',
    missionId: 'm3',
    skillTag: 'TensorFlow',
    reflection: 'Trained a classification model',
    createdAt: '2025-06-03T10:00:00Z',
    artifactUrl: 'https://github.com/example/repo',
  },
];

const MANY_EVIDENCE = Array.from({ length: 15 }, (_, i) => ({
  userId: 'u1',
  evidenceId: `e${i}`,
  missionId: `m${i}`,
  skillTag: i % 2 === 0 ? 'Python' : 'ML',
  reflection: `Evidence item ${i}`,
  createdAt: new Date(2025, 5, i + 1).toISOString(),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <Evidence />
    </MemoryRouter>,
  );
}

describe('Evidence', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseEvidence.mockReturnValue({
      evidence: [],
      loading: false,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
  });

  it('shows skeleton when loading', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: [],
      loading: true,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    expect(screen.queryByText('Evidence Vault')).not.toBeInTheDocument();
    expect(screen.queryByText('No evidence yet')).not.toBeInTheDocument();
  });

  it('shows error state with retry', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: [],
      loading: false,
      error: 'API unavailable',
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    expect(screen.getByText('Unable to load evidence')).toBeInTheDocument();
    expect(screen.getByText('API unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows empty state when no evidence', () => {
    renderPage();
    expect(screen.getByText('No evidence yet')).toBeInTheDocument();
    expect(screen.getByText('Go to Missions')).toBeInTheDocument();
  });

  it('renders heading with count', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: MOCK_EVIDENCE,
      loading: false,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    expect(screen.getByText('Evidence Vault')).toBeInTheDocument();
    expect(screen.getByText(/3 items across 2 skills/)).toBeInTheDocument();
  });

  it('renders skill coverage section', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: MOCK_EVIDENCE,
      loading: false,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    expect(screen.getByText('Skill Coverage')).toBeInTheDocument();
  });

  it('renders evidence cards with skill badge and reflection', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: MOCK_EVIDENCE,
      loading: false,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    expect(screen.getByText('Built a data pipeline using pandas')).toBeInTheDocument();
    expect(screen.getByText('Trained a classification model')).toBeInTheDocument();
  });

  it('renders artifact link when artifactUrl is present', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: MOCK_EVIDENCE,
      loading: false,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    const link = screen.getByText('View artifact');
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toHaveAttribute('target', '_blank');
    expect(link.closest('a')).toHaveAttribute('href', 'https://github.com/example/repo');
  });

  it('renders filter chips that can be toggled', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: MOCK_EVIDENCE,
      loading: false,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    // Click TensorFlow filter chip
    const chips = screen.getAllByRole('button');
    const tfChip = chips.find(
      btn => btn.textContent === 'TensorFlow' && btn.closest('section'),
    );
    expect(tfChip).toBeDefined();
    if (tfChip) {
      fireEvent.click(tfChip);
      expect(screen.getByText(/Showing 1 of 3 items/)).toBeInTheDocument();
    }
  });

  it('shows load more button when >10 items', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: MANY_EVIDENCE,
      loading: false,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    expect(screen.getByText('Load more')).toBeInTheDocument();
  });

  it('load more button shows additional items', () => {
    mockedUseEvidence.mockReturnValue({
      evidence: MANY_EVIDENCE,
      loading: false,
      error: null,
      fetchEvidence: mockFetchEvidence,
      nextCursor: null,
      loadMore: vi.fn(),
    });
    renderPage();
    fireEvent.click(screen.getByText('Load more'));
    // After loading more, all 15 items should be visible (or at least >10)
    expect(screen.queryByText('Load more')).not.toBeInTheDocument();
  });
});
