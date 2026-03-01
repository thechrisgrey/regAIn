import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useDashboard } from '../hooks/useDashboard';
import type { Campaign } from '../types';
import { DISPLAY_PHASES, phaseIndex, phaseProgress, daysActive, formatDate, phaseLabel } from '../utils/campaign';
import { Card, SectionLabel, ProgressBar, Button, SkeletonBlock } from '../components/ui';

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function Skeleton() {
  return (
    <div className="space-y-6">
      {/* Status bar */}
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-28" />
        <div className="mt-5 flex items-center gap-6">
          <SkeletonBlock className="h-3 w-20" />
          <SkeletonBlock className="h-px w-8" />
          <SkeletonBlock className="h-3 w-16" />
          <SkeletonBlock className="h-px w-8" />
          <SkeletonBlock className="h-3 w-14" />
        </div>
        <SkeletonBlock className="mt-4 h-1 w-full" />
        <div className="mt-6 flex gap-12">
          {[1, 2, 3].map(i => (
            <div key={i}>
              <SkeletonBlock className="h-8 w-10" />
              <SkeletonBlock className="mt-1.5 h-2 w-20" />
            </div>
          ))}
        </div>
      </Card>

      {/* Focus card */}
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-24" />
        <SkeletonBlock className="mt-5 h-6 w-64" />
        <SkeletonBlock className="mt-4 h-3.5 w-full" />
        <SkeletonBlock className="mt-2 h-3.5 w-3/4" />
        <SkeletonBlock className="mt-8 h-9 w-36" />
      </Card>

      {/* Two columns */}
      <div className="grid gap-6 sm:grid-cols-2">
        <Card className="p-6">
          <SkeletonBlock className="h-2.5 w-16" />
          <SkeletonBlock className="mt-5 h-10 w-12" />
          <SkeletonBlock className="mt-2 h-2.5 w-24" />
        </Card>
        <Card className="p-6">
          <SkeletonBlock className="h-2.5 w-24" />
          <div className="mt-5 space-y-3">
            <SkeletonBlock className="h-3.5 w-full" />
            <SkeletonBlock className="h-3.5 w-3/4" />
            <SkeletonBlock className="h-3.5 w-1/2" />
          </div>
        </Card>
      </div>

      {/* Market */}
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-28" />
        <SkeletonBlock className="mt-5 h-5 w-48" />
        <SkeletonBlock className="mt-3 h-3.5 w-full" />
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

function DashboardError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <p className="text-sm font-medium text-neutral-900">Unable to load dashboard</p>
      <p className="mt-1.5 text-sm text-neutral-500">{message}</p>
      <Button onClick={onRetry} className="mt-6">
        Retry
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section components
// ---------------------------------------------------------------------------

function CampaignStatus({
  campaign,
  missionsCompleted,
  evidenceCount,
}: {
  campaign: Campaign;
  missionsCompleted: number;
  evidenceCount: number;
}) {
  const idx = phaseIndex(campaign.phase);
  const progress = phaseProgress(campaign.phase);
  const days = daysActive(campaign.startDate);

  return (
    <Card variant="default" className="p-6">
      <SectionLabel>Campaign Progress</SectionLabel>

      {/* Phase indicator with step dots */}
      <div className="mt-4 flex items-center">
        {DISPLAY_PHASES.map((phase, i) => (
          <div key={phase} className="flex items-center">
            <div className="flex items-center gap-2">
              <div
                className={`h-2 w-2 rounded-full transition-colors ${
                  i < idx
                    ? 'bg-primary-500'
                    : i === idx
                      ? 'bg-primary-500 ring-4 ring-primary-100'
                      : 'bg-neutral-200'
                }`}
              />
              <span
                className={`text-sm transition-colors ${
                  i < idx
                    ? 'font-medium text-neutral-900'
                    : i === idx
                      ? 'font-semibold text-primary-600'
                      : 'font-normal text-neutral-300'
                }`}
              >
                {phase}
              </span>
            </div>
            {i < DISPLAY_PHASES.length - 1 && (
              <span
                className={`mx-3 inline-block h-px w-6 sm:w-10 ${
                  i < idx ? 'bg-primary-300' : 'bg-neutral-200'
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <ProgressBar value={progress} className="mt-3" />

      {/* Metrics as distinct cells */}
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-3xl font-medium font-mono tabular-nums">
            {missionsCompleted}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">missions completed</p>
        </div>
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-3xl font-medium font-mono tabular-nums">
            {evidenceCount}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">evidence items</p>
        </div>
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-3xl font-medium font-mono tabular-nums">{days}</p>
          <p className="mt-0.5 text-xs text-neutral-500">days active</p>
        </div>
      </div>

      {/* Date */}
      <p className="mt-4 text-xs text-neutral-400">
        Started {formatDate(campaign.startDate)}
      </p>
    </Card>
  );
}

function CurrentFocus({ campaign }: { campaign: Campaign }) {
  const label = phaseLabel(campaign.phase);

  return (
    <Card variant="accent" className="p-6">
      <SectionLabel>Current Focus</SectionLabel>

      <p className="mt-4 text-2xl font-semibold tracking-tight text-neutral-900">
        {campaign.targetRole}
      </p>

      <p className="mt-3 text-sm leading-relaxed text-neutral-500">
        You are in the{' '}
        <span className="font-medium text-neutral-700">{label}</span> phase.
        Your daily missions build documented evidence for this transition.
        Each completed mission strengthens your profile and moves you closer
        to your target.
      </p>

      {campaign.skillsFocus.length > 0 && (
        <div className="mt-4">
          <p className="text-xs text-neutral-400">Skills in focus</p>
          <p className="mt-1 text-sm text-neutral-600">
            {campaign.skillsFocus.join(' \u00b7 ')}
          </p>
        </div>
      )}

      <div className="mt-6">
        <Link
          to="/missions"
          className="inline-flex items-center gap-2 rounded-[var(--radius-button)] bg-primary-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-600 transition-colors duration-150"
        >
          Go to Missions
          <svg
            className="h-3.5 w-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"
            />
          </svg>
        </Link>
      </div>
    </Card>
  );
}

function EvidenceStats({ count }: { count: number }) {
  return (
    <Card className="p-6">
      <SectionLabel>Evidence</SectionLabel>

      <p className="mt-4 text-4xl font-medium font-mono tabular-nums text-neutral-900">{count}</p>
      <p className="mt-1 text-xs text-neutral-400">
        {count === 1 ? 'item recorded' : 'items recorded'}
      </p>

      {count === 0 && (
        <p className="mt-4 text-sm leading-relaxed text-neutral-500">
          Complete missions to begin building your evidence vault.
        </p>
      )}

      <div className="mt-6">
        <Link
          to="/evidence"
          className="text-sm font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
        >
          View evidence
          <span className="ml-1">&rarr;</span>
        </Link>
      </div>
    </Card>
  );
}

function SkillCoverage({ skills }: { skills: string[] }) {
  return (
    <Card className="p-6">
      <SectionLabel>Skill Focus</SectionLabel>

      {skills.length > 0 ? (
        <div className="mt-4 space-y-2.5">
          {skills.slice(0, 8).map(skill => (
            <div key={skill} className="flex items-center gap-3">
              <div className="h-3.5 w-0.5 bg-primary-500/50" />
              <span className="text-sm text-neutral-600">{skill}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm leading-relaxed text-neutral-500">
          Complete missions to build your skill portfolio.
        </p>
      )}

      <div className="mt-6">
        <Link
          to="/evidence"
          className="text-sm font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
        >
          See all
          <span className="ml-1">&rarr;</span>
        </Link>
      </div>
    </Card>
  );
}

function MarketPosition({ campaign }: { campaign: Campaign }) {
  return (
    <Card className="p-6">
      <SectionLabel>Market Position</SectionLabel>

      <p className="mt-4 text-lg font-semibold text-neutral-900">
        {campaign.targetRole}
      </p>

      <p className="mt-2 text-sm leading-relaxed text-neutral-500">
        Market alignment data builds as you complete missions and accumulate
        evidence. Your skill focus areas are already calibrated to demand
        for this role.
      </p>

      {campaign.skillsFocus.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1">
          {campaign.skillsFocus.map(skill => (
            <span key={skill} className="text-sm text-neutral-600">{skill}</span>
          ))}
        </div>
      )}

      <div className="mt-6">
        <Link
          to="/missions"
          className="text-sm font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
        >
          Explore missions
          <span className="ml-1">&rarr;</span>
        </Link>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function Dashboard() {
  const { data, loading, error, fetchDashboard } = useDashboard();

  useEffect(() => {
    void fetchDashboard();
  }, [fetchDashboard]);

  if (loading || (!data && !error)) {
    return <Skeleton />;
  }

  if (error) {
    return <DashboardError message={error} onRetry={() => void fetchDashboard()} />;
  }

  if (!data) return null;

  const { campaign, stats } = data;

  if (!campaign) {
    return (
      <div className="space-y-6 animate-fade-in">
        <Card className="p-10 text-center">
          <img
            src="/regain-type.png"
            alt="Regain"
            className="mx-auto h-12 w-auto"
          />
          <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-neutral-500">
            Set up your career campaign to start generating missions, building evidence, and tracking your professional trajectory.
          </p>
          <div className="section-divider mx-auto mt-6 w-32" />
          <div className="mt-6">
            <Link to="/onboarding">
              <Button size="lg">Get started</Button>
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Dashboard</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Tracking your transition to {campaign.targetRole}
          </p>
        </div>
        <p className="text-xs font-mono tabular-nums text-neutral-400">
          {new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
        </p>
      </div>

      <CampaignStatus
        campaign={campaign}
        missionsCompleted={stats.missionsCompleted}
        evidenceCount={stats.evidenceCount}
      />

      <CurrentFocus campaign={campaign} />

      <div className="grid gap-6 sm:grid-cols-2">
        <EvidenceStats count={stats.evidenceCount} />
        <SkillCoverage skills={campaign.skillsFocus} />
      </div>

      <MarketPosition campaign={campaign} />
    </div>
  );
}
