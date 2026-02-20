import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useDashboard } from '../hooks/useDashboard';
import type { Campaign } from '../types';

// ---------------------------------------------------------------------------
// Phase mapping
// ---------------------------------------------------------------------------

const DISPLAY_PHASES = ['Foundation', 'Expansion', 'Launch'] as const;

function phaseIndex(phase: Campaign['phase']): number {
  switch (phase) {
    case 'foundation':
      return 0;
    case 'momentum':
    case 'acceleration':
      return 1;
    case 'transition':
      return 2;
  }
}

function phaseLabel(phase: Campaign['phase']): string {
  return DISPLAY_PHASES[phaseIndex(phase)];
}

function phaseProgress(phase: Campaign['phase']): number {
  switch (phase) {
    case 'foundation':
      return 33;
    case 'momentum':
      return 50;
    case 'acceleration':
      return 66;
    case 'transition':
      return 100;
  }
}

function daysActive(startDate: string): number {
  const start = new Date(startDate);
  const now = new Date();
  return Math.max(1, Math.floor((now.getTime() - start.getTime()) / 86400000));
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function Skeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Status bar */}
      <div className="rounded-sm border border-slate-200 bg-white p-6">
        <div className="h-2.5 w-28 rounded-sm bg-slate-100" />
        <div className="mt-5 flex items-center gap-6">
          <div className="h-3 w-20 rounded-sm bg-slate-100" />
          <div className="h-px w-8 bg-slate-100" />
          <div className="h-3 w-16 rounded-sm bg-slate-100" />
          <div className="h-px w-8 bg-slate-100" />
          <div className="h-3 w-14 rounded-sm bg-slate-100" />
        </div>
        <div className="mt-4 h-1 w-full rounded-sm bg-slate-100" />
        <div className="mt-6 flex gap-12">
          {[1, 2, 3].map(i => (
            <div key={i}>
              <div className="h-8 w-10 rounded-sm bg-slate-100" />
              <div className="mt-1.5 h-2 w-20 rounded-sm bg-slate-100" />
            </div>
          ))}
        </div>
      </div>

      {/* Focus card */}
      <div className="rounded-sm border border-slate-200 bg-white p-6">
        <div className="h-2.5 w-24 rounded-sm bg-slate-100" />
        <div className="mt-5 h-6 w-64 rounded-sm bg-slate-100" />
        <div className="mt-4 h-3.5 w-full rounded-sm bg-slate-100" />
        <div className="mt-2 h-3.5 w-3/4 rounded-sm bg-slate-100" />
        <div className="mt-8 h-9 w-36 rounded-sm bg-slate-100" />
      </div>

      {/* Two columns */}
      <div className="grid gap-6 sm:grid-cols-2">
        <div className="rounded-sm border border-slate-200 bg-white p-6">
          <div className="h-2.5 w-16 rounded-sm bg-slate-100" />
          <div className="mt-5 h-10 w-12 rounded-sm bg-slate-100" />
          <div className="mt-2 h-2.5 w-24 rounded-sm bg-slate-100" />
        </div>
        <div className="rounded-sm border border-slate-200 bg-white p-6">
          <div className="h-2.5 w-24 rounded-sm bg-slate-100" />
          <div className="mt-5 space-y-3">
            <div className="h-3.5 w-full rounded-sm bg-slate-100" />
            <div className="h-3.5 w-3/4 rounded-sm bg-slate-100" />
            <div className="h-3.5 w-1/2 rounded-sm bg-slate-100" />
          </div>
        </div>
      </div>

      {/* Market */}
      <div className="rounded-sm border border-slate-200 bg-white p-6">
        <div className="h-2.5 w-28 rounded-sm bg-slate-100" />
        <div className="mt-5 h-5 w-48 rounded-sm bg-slate-100" />
        <div className="mt-3 h-3.5 w-full rounded-sm bg-slate-100" />
      </div>
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
      <p className="text-sm font-medium text-slate-900">Unable to load dashboard</p>
      <p className="mt-1.5 text-sm text-slate-500">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-6 rounded-sm bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 transition-colors"
      >
        Retry
      </button>
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
    <section className="rounded-sm border border-slate-200 bg-white p-6">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Campaign
      </p>

      {/* Phase indicator */}
      <div className="mt-4 flex items-center">
        {DISPLAY_PHASES.map((phase, i) => (
          <div key={phase} className="flex items-center">
            <span
              className={`text-sm transition-colors ${
                i < idx
                  ? 'font-medium text-slate-900'
                  : i === idx
                    ? 'font-semibold text-indigo-600'
                    : 'font-normal text-slate-300'
              }`}
            >
              {phase}
            </span>
            {i < DISPLAY_PHASES.length - 1 && (
              <span
                className={`mx-3 inline-block h-px w-6 sm:w-10 ${
                  i < idx ? 'bg-slate-400' : 'bg-slate-200'
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="mt-3 h-1 w-full overflow-hidden rounded-sm bg-slate-100">
        <div
          className="h-full bg-indigo-600 transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Metrics */}
      <div className="mt-6 flex gap-8 sm:gap-12">
        <div>
          <p className="text-3xl font-medium tabular-nums text-slate-900">
            {missionsCompleted}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">missions completed</p>
        </div>
        <div>
          <p className="text-3xl font-medium tabular-nums text-slate-900">
            {evidenceCount}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">evidence items</p>
        </div>
        <div>
          <p className="text-3xl font-medium tabular-nums text-slate-900">{days}</p>
          <p className="mt-0.5 text-xs text-slate-400">days active</p>
        </div>
      </div>

      {/* Date */}
      <p className="mt-4 text-xs text-slate-400">
        Started {formatDate(campaign.startDate)}
      </p>
    </section>
  );
}

function CurrentFocus({ campaign }: { campaign: Campaign }) {
  const label = phaseLabel(campaign.phase);

  return (
    <section className="rounded-sm border border-indigo-500/20 bg-white p-6">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Current Focus
      </p>

      <p className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">
        {campaign.targetRole}
      </p>

      <p className="mt-3 text-sm leading-relaxed text-slate-500">
        You are in the{' '}
        <span className="font-medium text-slate-700">{label}</span> phase.
        Your daily missions build documented evidence for this transition.
        Each completed mission strengthens your profile and moves you closer
        to your target.
      </p>

      {campaign.skillsFocus.length > 0 && (
        <div className="mt-4">
          <p className="text-xs text-slate-400">Skills in focus</p>
          <p className="mt-1 text-sm text-slate-600">
            {campaign.skillsFocus.join(' \u00b7 ')}
          </p>
        </div>
      )}

      <div className="mt-6">
        <Link
          to="/missions"
          className="inline-flex items-center gap-2 rounded-sm bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
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
    </section>
  );
}

function EvidenceStats({ count }: { count: number }) {
  return (
    <section className="rounded-sm border border-slate-200 bg-white p-6">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Evidence
      </p>

      <p className="mt-4 text-4xl font-medium tabular-nums text-slate-900">{count}</p>
      <p className="mt-1 text-xs text-slate-400">
        {count === 1 ? 'item recorded' : 'items recorded'}
      </p>

      {count === 0 && (
        <p className="mt-4 text-sm leading-relaxed text-slate-500">
          Complete missions to begin building your evidence vault.
        </p>
      )}

      <div className="mt-6">
        <Link
          to="/evidence"
          className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
        >
          View evidence
          <span className="ml-1">&rarr;</span>
        </Link>
      </div>
    </section>
  );
}

function SkillCoverage({ skills }: { skills: string[] }) {
  return (
    <section className="rounded-sm border border-slate-200 bg-white p-6">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Skill Focus
      </p>

      {skills.length > 0 ? (
        <div className="mt-4 space-y-2.5">
          {skills.slice(0, 8).map(skill => (
            <div key={skill} className="flex items-center gap-3">
              <div className="h-3.5 w-0.5 bg-indigo-600/50" />
              <span className="text-sm text-slate-600">{skill}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm leading-relaxed text-slate-500">
          Complete missions to build your skill portfolio.
        </p>
      )}

      <div className="mt-6">
        <Link
          to="/evidence"
          className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
        >
          See all
          <span className="ml-1">&rarr;</span>
        </Link>
      </div>
    </section>
  );
}

function MarketPosition({ campaign }: { campaign: Campaign }) {
  return (
    <section className="rounded-sm border border-slate-200 bg-white p-6">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Market Position
      </p>

      <p className="mt-4 text-lg font-semibold text-slate-900">
        {campaign.targetRole}
      </p>

      <p className="mt-2 text-sm leading-relaxed text-slate-500">
        Market alignment data builds as you complete missions and accumulate
        evidence. Your skill focus areas are already calibrated to demand
        for this role.
      </p>

      {campaign.skillsFocus.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1">
          {campaign.skillsFocus.map(skill => (
            <span key={skill} className="text-sm text-slate-600">{skill}</span>
          ))}
        </div>
      )}

      <div className="mt-6">
        <Link
          to="/missions"
          className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
        >
          Explore missions
          <span className="ml-1">&rarr;</span>
        </Link>
      </div>
    </section>
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

  return (
    <div className="space-y-6 animate-fade-in">
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
