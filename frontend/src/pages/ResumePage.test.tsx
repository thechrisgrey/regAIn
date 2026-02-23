import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ResumePage from './ResumePage';

// Mock useResume hook
const mockFetchResume = vi.fn();
const mockRegenerateResume = vi.fn();

vi.mock('../hooks/useResume', () => ({
  useResume: vi.fn(() => ({
    resume: null,
    loading: false,
    regenerating: false,
    error: null,
    fetchResume: mockFetchResume,
    regenerateResume: mockRegenerateResume,
  })),
}));

import { useResume } from '../hooks/useResume';
const mockedUseResume = vi.mocked(useResume);

const MOCK_RESUME = {
  content: '---\nschema_version: "1.0"\n---\n## Professional Summary\nTest summary.',
  generatedAt: new Date().toISOString(),
  version: 3,
  downloadUrl: 'https://s3.amazonaws.com/test-bucket/resume.md',
  frontmatter: {
    schema_version: '1.0',
    generated_at: new Date().toISOString(),
    regain_version: '1.0.0',
    name: 'Jane Smith',
    target_role: 'AI QA Engineer',
    transition_type: 'veteran',
    skills: [
      {
        skill_name: 'Python Testing',
        evidence_count: 8,
        strongest_evidence_summary: 'Built automated test suite',
        proficiency_indicator: 'advanced',
      },
    ],
    campaign_phase: 'expansion',
    campaign_progress_pct: 65,
    market_alignment_score: 72,
    missions_completed: 23,
    evidence_items: 31,
    top_accomplishments: ['Built automated test suite covering 3 ML pipeline stages'],
  },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ResumePage />
    </MemoryRouter>,
  );
}

describe('ResumePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseResume.mockReturnValue({
      resume: null,
      loading: false,
      regenerating: false,
      error: null,
      fetchResume: mockFetchResume,
      regenerateResume: mockRegenerateResume,
    });
  });

  it('shows empty state when no resume exists (Req 9.7)', () => {
    renderPage();
    expect(screen.getByText('No resume yet')).toBeInTheDocument();
    expect(screen.getByText(/Generate your resume from completed missions/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Generate Resume/ })).toBeInTheDocument();
  });

  it('shows loading indicator during fetch (Req 9.8)', () => {
    mockedUseResume.mockReturnValue({
      resume: null,
      loading: true,
      regenerating: false,
      error: null,
      fetchResume: mockFetchResume,
      regenerateResume: mockRegenerateResume,
    });
    renderPage();
    // Skeleton renders SkeletonBlock elements (animated placeholders)
    expect(screen.queryByText('No resume yet')).not.toBeInTheDocument();
    expect(screen.queryByText('Resume Overview')).not.toBeInTheDocument();
  });

  it('renders frontmatter as structured metadata (Req 9.3)', () => {
    mockedUseResume.mockReturnValue({
      resume: MOCK_RESUME,
      loading: false,
      regenerating: false,
      error: null,
      fetchResume: mockFetchResume,
      regenerateResume: mockRegenerateResume,
    });
    renderPage();
    expect(screen.getByText('Resume Overview')).toBeInTheDocument();
    expect(screen.getByText('AI QA Engineer')).toBeInTheDocument();
    expect(screen.getByText('23')).toBeInTheDocument();
    expect(screen.getByText('31')).toBeInTheDocument();
    expect(screen.getByText('72%')).toBeInTheDocument();
    expect(screen.getByText('Python Testing')).toBeInTheDocument();
    expect(screen.getByText('Advanced')).toBeInTheDocument();
  });

  it('shows Download .md button (Req 9.4)', () => {
    mockedUseResume.mockReturnValue({
      resume: MOCK_RESUME,
      loading: false,
      regenerating: false,
      error: null,
      fetchResume: mockFetchResume,
      regenerateResume: mockRegenerateResume,
    });
    renderPage();
    const downloadLink = screen.getByText('Download .md');
    expect(downloadLink).toBeInTheDocument();
    expect(downloadLink.closest('a')).toHaveAttribute('href', MOCK_RESUME.downloadUrl);
  });

  it('shows Regenerate button that calls POST endpoint (Req 9.5)', () => {
    mockedUseResume.mockReturnValue({
      resume: MOCK_RESUME,
      loading: false,
      regenerating: false,
      error: null,
      fetchResume: mockFetchResume,
      regenerateResume: mockRegenerateResume,
    });
    renderPage();
    const button = screen.getByRole('button', { name: 'Regenerate' });
    expect(button).toBeInTheDocument();
    fireEvent.click(button);
    expect(mockRegenerateResume).toHaveBeenCalled();
  });

  it('shows version indicator (Req 9.6)', () => {
    mockedUseResume.mockReturnValue({
      resume: MOCK_RESUME,
      loading: false,
      regenerating: false,
      error: null,
      fetchResume: mockFetchResume,
      regenerateResume: mockRegenerateResume,
    });
    renderPage();
    expect(screen.getByText(/Version 3/)).toBeInTheDocument();
    expect(screen.getByText(/Generated/)).toBeInTheDocument();
  });

  it('disables Regenerate button during regeneration (Req 9.9)', () => {
    mockedUseResume.mockReturnValue({
      resume: MOCK_RESUME,
      loading: false,
      regenerating: true,
      error: null,
      fetchResume: mockFetchResume,
      regenerateResume: mockRegenerateResume,
    });
    renderPage();
    const button = screen.getByRole('button', { name: 'Regenerating…' });
    expect(button).toBeDisabled();
  });

  it('shows error state with retry (Req 9.8)', () => {
    mockedUseResume.mockReturnValue({
      resume: null,
      loading: false,
      regenerating: false,
      error: 'Network error',
      fetchResume: mockFetchResume,
      regenerateResume: mockRegenerateResume,
    });
    renderPage();
    expect(screen.getByText('Unable to load resume')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});