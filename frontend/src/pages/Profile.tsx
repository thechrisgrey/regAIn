import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useDashboard } from '../hooks/useDashboard';
import type { Campaign } from '../types';

// ---------------------------------------------------------------------------
// Phase mapping (consistent with Dashboard)
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
      {/* Identity */}
      <div className="rounded-sm border border-slate-200 bg-white p-8">
        <div className="h-2.5 w-36 rounded-sm bg-slate-100" />
        <div className="mt-6 h-8 w-72 rounded-sm bg-slate-100" />
        <div className="mt-3 flex items-center gap-3">
          <div className="h-5 w-20 rounded-sm bg-slate-100" />
          <div className="h-3.5 w-40 rounded-sm bg-slate-100" />
        </div>
        <div className="mt-8 flex gap-10">
          {[1, 2, 3].map(i => (
            <div key={i}>
              <div className="h-8 w-10 rounded-sm bg-slate-100" />
              <div className="mt-1.5 h-2.5 w-24 rounded-sm bg-slate-100" />
            </div>
          ))}
        </div>
        <div className="mt-4 h-2.5 w-44 rounded-sm bg-slate-100" />
      </div>

      {/* Skills */}
      <div className="rounded-sm border border-slate-200 bg-white p-6">
        <div className="h-2.5 w-28 rounded-sm bg-slate-100" />
        <div className="mt-5 flex flex-wrap gap-2.5">
          {[80, 108, 64, 92, 120, 72].map((w, i) => (
            <div
              key={i}
              className="h-8 rounded-sm bg-slate-100"
              style={{ width: `${w}px` }}
            />
          ))}
        </div>
      </div>

      {/* Campaign */}
      <div className="rounded-sm border border-slate-200 bg-white p-6">
        <div className="h-2.5 w-36 rounded-sm bg-slate-100" />
        <div className="mt-5 flex items-center gap-6">
          <div className="h-3 w-20 rounded-sm bg-slate-100" />
          <div className="h-px w-8 bg-slate-100" />
          <div className="h-3 w-16 rounded-sm bg-slate-100" />
          <div className="h-px w-8 bg-slate-100" />
          <div className="h-3 w-14 rounded-sm bg-slate-100" />
        </div>
        <div className="mt-3 h-1 w-full rounded-sm bg-slate-100" />
        <div className="mt-6 h-5 w-56 rounded-sm bg-slate-100" />
        <div className="mt-4 h-3 w-44 rounded-sm bg-slate-100" />
        <div className="mt-6 flex flex-wrap gap-2">
          {[72, 96, 80].map((w, i) => (
            <div
              key={i}
              className="h-6 rounded-sm bg-slate-100"
              style={{ width: `${w}px` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

function ProfileError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <p className="text-sm font-medium text-slate-900">Unable to load profile</p>
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
// Section 1: Identity Summary
// ---------------------------------------------------------------------------

function IdentitySummary({
  username,
  campaign,
  stats,
}: {
  username: string;
  campaign: Campaign;
  stats: { missionsCompleted: number; evidenceCount: number };
}) {
  const days = daysActive(campaign.startDate);
  const idx = phaseIndex(campaign.phase);

  return (
    <section className="rounded-sm border border-slate-200 bg-white p-8">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Transition Profile
      </p>

      <p className="mt-5 text-2xl font-semibold tracking-tight text-slate-900">
        {campaign.targetRole}
      </p>

      <div className="mt-2.5 flex flex-wrap items-center gap-3">
        <span className="inline-block rounded-sm bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-widest text-indigo-600">
          {DISPLAY_PHASES[idx]}
        </span>
        <span className="text-sm text-slate-400">{username}</span>
      </div>

      <div className="mt-8 flex gap-8 sm:gap-12">
        <div>
          <p className="text-3xl font-medium tabular-nums text-slate-900">{days}</p>
          <p className="mt-0.5 text-xs text-slate-400">days active</p>
        </div>
        <div>
          <p className="text-3xl font-medium tabular-nums text-slate-900">
            {stats.missionsCompleted}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">missions completed</p>
        </div>
        <div>
          <p className="text-3xl font-medium tabular-nums text-slate-900">
            {stats.evidenceCount}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">evidence items</p>
        </div>
      </div>

      <p className="mt-4 text-xs text-slate-400">
        Campaign started {formatDate(campaign.startDate)}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 2: Skills Inventory
// ---------------------------------------------------------------------------

function SkillsInventory({ skills }: { skills: string[] }) {
  return (
    <section className="rounded-sm border border-slate-200 bg-white p-6">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Skills in Focus
      </p>

      {skills.length > 0 ? (
        <div className="mt-5 flex flex-wrap gap-2.5">
          {skills.map(skill => (
            <span
              key={skill}
              className="rounded-sm bg-slate-100 px-3 py-1.5 text-sm text-slate-700"
            >
              {skill}
            </span>
          ))}
        </div>
      ) : (
        <div className="mt-5">
          <p className="text-sm leading-relaxed text-slate-500">
            Skills will be populated as you complete missions and build your
            evidence portfolio.
          </p>
          <div className="mt-4">
            <Link
              to="/missions"
              className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
            >
              Go to missions
              <span className="ml-1">&rarr;</span>
            </Link>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section 3: Campaign Journey
// ---------------------------------------------------------------------------

function CampaignJourney({ campaign }: { campaign: Campaign }) {
  const idx = phaseIndex(campaign.phase);
  const progress = phaseProgress(campaign.phase);
  const days = daysActive(campaign.startDate);

  return (
    <section className="rounded-sm border border-slate-200 bg-white p-6">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
        Campaign Journey
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

      {/* Trajectory */}
      <p className="mt-6 text-lg font-semibold text-slate-900">
        {campaign.targetRole}
      </p>
      <p className="mt-1 text-xs text-slate-400">
        Started {formatDate(campaign.startDate)} &middot;{' '}
        <span className="tabular-nums">{days}</span> days active
      </p>

      {/* Focus skills with accent */}
      {campaign.skillsFocus.length > 0 && (
        <div className="mt-5 border-t border-slate-100 pt-5">
          <p className="text-xs text-slate-400">Campaign skill focus</p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {campaign.skillsFocus.map(skill => (
              <span
                key={skill}
                className="rounded-sm bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-600"
              >
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6">
        <Link
          to="/dashboard"
          className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
        >
          View full campaign details
          <span className="ml-1">&rarr;</span>
        </Link>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function Profile() {
  const { user } = useAuth();
  const { data, loading, error, fetchDashboard } = useDashboard();

  useEffect(() => {
    void fetchDashboard();
  }, [fetchDashboard]);

  if (loading || (!data && !error)) {
    return <Skeleton />;
  }

  if (error) {
    return (
      <ProfileError message={error} onRetry={() => void fetchDashboard()} />
    );
  }

  if (!data) return null;

  const { campaign, stats } = data;

  return (
    <div className="space-y-6 animate-fade-in">
      <IdentitySummary
        username={user?.username ?? ''}
        campaign={campaign}
        stats={stats}
      />

      <SkillsInventory skills={campaign.skillsFocus} />

      <CampaignJourney campaign={campaign} />
    </div>
  );
}
