import { useEffect, useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useEvidence } from '../hooks/useEvidence';
import type { Evidence as EvidenceType } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);
  const diffWeek = Math.floor(diffDay / 7);
  const diffMonth = Math.floor(diffDay / 30);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60)
    return `${diffMin} ${diffMin === 1 ? 'minute' : 'minutes'} ago`;
  if (diffHour < 24)
    return `${diffHour} ${diffHour === 1 ? 'hour' : 'hours'} ago`;
  if (diffDay === 1) return 'Yesterday';
  if (diffDay < 7) return `${diffDay} days ago`;
  if (diffWeek < 5)
    return `${diffWeek} ${diffWeek === 1 ? 'week' : 'weeks'} ago`;
  if (diffMonth < 12)
    return `${diffMonth} ${diffMonth === 1 ? 'month' : 'months'} ago`;

  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SkillStat {
  skill: string;
  count: number;
  ratio: number;
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function Skeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Skill coverage */}
      <div className="rounded-sm border border-slate-200 bg-white p-6">
        <div className="h-2.5 w-28 rounded-sm bg-slate-100" />
        <div className="mt-5 space-y-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="flex items-center gap-4">
              <div className="h-3 w-24 rounded-sm bg-slate-100" />
              <div className="h-1.5 flex-1 rounded-sm bg-slate-100" />
              <div className="h-3 w-6 rounded-sm bg-slate-100" />
            </div>
          ))}
        </div>
        <div className="mt-6 flex gap-12">
          {[1, 2].map(i => (
            <div key={i}>
              <div className="h-8 w-10 rounded-sm bg-slate-100" />
              <div className="mt-1.5 h-2 w-20 rounded-sm bg-slate-100" />
            </div>
          ))}
        </div>
      </div>

      {/* Filter row placeholder */}
      <div>
        <div className="h-2.5 w-20 rounded-sm bg-slate-100" />
        <div className="mt-4 flex gap-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-7 w-20 rounded-sm bg-slate-100" />
          ))}
        </div>
      </div>

      {/* Evidence cards */}
      <div className="space-y-4">
        {[1, 2, 3].map(i => (
          <div
            key={i}
            className="rounded-sm border border-slate-200 bg-white p-6"
          >
            <div className="h-5 w-24 rounded-sm bg-slate-100" />
            <div className="mt-4 h-3.5 w-full rounded-sm bg-slate-100" />
            <div className="mt-2 h-3.5 w-4/5 rounded-sm bg-slate-100" />
            <div className="mt-2 h-3.5 w-3/5 rounded-sm bg-slate-100" />
            <div className="mt-4 flex gap-6">
              <div className="h-3 w-24 rounded-sm bg-slate-100" />
              <div className="h-3 w-32 rounded-sm bg-slate-100" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

function EvidenceError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <p className="text-sm font-medium text-slate-900">
        Unable to load evidence
      </p>
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
// Empty state
// ---------------------------------------------------------------------------

function EmptyEvidence() {
  return (
    <section className="rounded-sm border border-slate-200 bg-white p-8">
      <div className="flex flex-col items-center py-12 text-center">
        <p className="text-xl font-semibold text-slate-900">No evidence yet</p>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-slate-500">
          Complete missions to start building your evidence portfolio. Each
          mission creates a timestamped record of demonstrated capability.
        </p>
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
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Skill coverage bar
// ---------------------------------------------------------------------------

function SkillCoverageBar({
  skill,
  count,
  ratio,
  dimmed,
}: {
  skill: string;
  count: number;
  ratio: number;
  dimmed: boolean;
}) {
  let barClass = 'bg-indigo-600/20';
  if (count >= 5) barClass = 'bg-indigo-600';
  else if (count >= 3) barClass = 'bg-indigo-600/50';

  return (
    <div
      className={`flex items-center gap-4 transition-opacity duration-200 ${
        dimmed ? 'opacity-30' : ''
      }`}
    >
      <span className="w-32 shrink-0 truncate text-sm text-slate-600">
        {skill}
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-sm bg-slate-100">
        <div
          className={`h-full rounded-sm transition-all duration-500 ${barClass}`}
          style={{ width: `${Math.max(ratio * 100, 4)}%` }}
        />
      </div>
      <span className="w-6 text-right text-xs tabular-nums text-slate-400">
        {count}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skill filter chips
// ---------------------------------------------------------------------------

function SkillFilterChips({
  skills,
  activeFilters,
  onToggle,
}: {
  skills: SkillStat[];
  activeFilters: Set<string>;
  onToggle: (skill: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {skills.map(({ skill }) => {
        const isActive = activeFilters.has(skill);
        return (
          <button
            key={skill}
            type="button"
            onClick={() => onToggle(skill)}
            className={`rounded-sm px-3 py-1.5 text-xs font-medium transition-colors ${
              isActive
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {skill}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evidence card
// ---------------------------------------------------------------------------

function EvidenceCard({
  entry,
  tagIntensity,
}: {
  entry: EvidenceType;
  tagIntensity: 'low' | 'medium' | 'high';
}) {
  let tagClass = 'bg-indigo-50 text-indigo-600';
  if (tagIntensity === 'high') tagClass = 'bg-indigo-100 text-indigo-700';
  else if (tagIntensity === 'medium')
    tagClass = 'bg-indigo-50/80 text-indigo-600';

  return (
    <div className="rounded-sm border border-slate-200 bg-white p-6">
      {/* Skill tag */}
      <span
        className={`inline-block rounded-sm px-2.5 py-1 text-xs font-medium ${tagClass}`}
      >
        {entry.skillTag}
      </span>

      {/* Reflection — the primary content */}
      <p className="mt-4 text-sm leading-relaxed text-slate-700">
        {entry.reflection}
      </p>

      {/* Artifact link */}
      {entry.artifactUrl && (
        <a
          href={entry.artifactUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors"
        >
          <svg
            className="h-3 w-3"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
            />
          </svg>
          View artifact
        </a>
      )}

      {/* Metadata */}
      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-1">
        <span className="text-xs text-slate-400">
          {relativeTime(entry.createdAt)}
        </span>
        <span className="text-xs tabular-nums text-slate-300">
          {entry.evidenceId}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function Evidence() {
  const { evidence, loading, error, fetchEvidence } = useEvidence();
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set());
  const [visibleCount, setVisibleCount] = useState(10);
  const [showAllSkills, setShowAllSkills] = useState(false);

  useEffect(() => {
    void fetchEvidence();
  }, [fetchEvidence]);

  // Compute skill stats from evidence
  const skillStats = useMemo<SkillStat[]>(() => {
    const counts = new Map<string, number>();
    for (const e of evidence) {
      counts.set(e.skillTag, (counts.get(e.skillTag) ?? 0) + 1);
    }
    const sorted = [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([skill, count]) => ({ skill, count, ratio: 0 }));

    const max = sorted.length > 0 ? sorted[0].count : 1;
    for (const stat of sorted) {
      stat.ratio = stat.count / max;
    }
    return sorted;
  }, [evidence]);

  // Map skill → intensity for card tag styling
  const skillIntensityMap = useMemo(() => {
    const map = new Map<string, 'low' | 'medium' | 'high'>();
    for (const { skill, count } of skillStats) {
      if (count >= 5) map.set(skill, 'high');
      else if (count >= 3) map.set(skill, 'medium');
      else map.set(skill, 'low');
    }
    return map;
  }, [skillStats]);

  // Filtered and sorted evidence
  const filteredEvidence = useMemo(() => {
    const sorted = [...evidence].sort(
      (a, b) =>
        new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    );
    if (activeFilters.size === 0) return sorted;
    return sorted.filter(e => activeFilters.has(e.skillTag));
  }, [evidence, activeFilters]);

  const visibleEvidence = filteredEvidence.slice(0, visibleCount);
  const hasMore = filteredEvidence.length > visibleCount;

  function toggleFilter(skill: string) {
    setActiveFilters(prev => {
      const next = new Set(prev);
      if (next.has(skill)) {
        next.delete(skill);
      } else {
        next.add(skill);
      }
      return next;
    });
    setVisibleCount(10);
  }

  // Loading
  if (loading && evidence.length === 0) {
    return <Skeleton />;
  }

  // Error
  if (error && evidence.length === 0) {
    return (
      <EvidenceError message={error} onRetry={() => void fetchEvidence()} />
    );
  }

  // Empty
  if (evidence.length === 0) {
    return (
      <div className="animate-fade-in">
        <EmptyEvidence />
      </div>
    );
  }

  const visibleSkillBars = showAllSkills
    ? skillStats
    : skillStats.slice(0, 8);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Section 1: Skill Coverage */}
      <section className="rounded-sm border border-slate-200 bg-white p-6">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          Skill Coverage
        </p>

        <div className="mt-5 space-y-3">
          {visibleSkillBars.map(stat => (
            <SkillCoverageBar
              key={stat.skill}
              skill={stat.skill}
              count={stat.count}
              ratio={stat.ratio}
              dimmed={
                activeFilters.size > 0 && !activeFilters.has(stat.skill)
              }
            />
          ))}
        </div>

        {skillStats.length > 8 && !showAllSkills && (
          <button
            type="button"
            onClick={() => setShowAllSkills(true)}
            className="mt-3 text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors"
          >
            Show all skills<span className="ml-1">&rarr;</span>
          </button>
        )}

        {/* Summary numbers */}
        <div className="mt-6 flex gap-12">
          <div>
            <p className="text-3xl font-medium tabular-nums text-slate-900">
              {evidence.length}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">total items</p>
          </div>
          <div>
            <p className="text-3xl font-medium tabular-nums text-slate-900">
              {skillStats.length}
            </p>
            <p className="mt-0.5 text-xs text-slate-400">skills covered</p>
          </div>
        </div>
      </section>

      {/* Section 2: Evidence Feed */}
      <section>
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            Evidence
          </p>
          {activeFilters.size > 0 && (
            <p className="text-xs text-slate-400">
              Showing {filteredEvidence.length} of {evidence.length} items
            </p>
          )}
        </div>

        {/* Filter chips */}
        {skillStats.length > 0 && (
          <div className="mt-4">
            <SkillFilterChips
              skills={skillStats}
              activeFilters={activeFilters}
              onToggle={toggleFilter}
            />
          </div>
        )}

        {/* Evidence cards */}
        <div className="mt-4 space-y-4">
          {visibleEvidence.map(entry => (
            <EvidenceCard
              key={entry.evidenceId}
              entry={entry}
              tagIntensity={skillIntensityMap.get(entry.skillTag) ?? 'low'}
            />
          ))}
        </div>

        {/* Filtered empty state */}
        {activeFilters.size > 0 && filteredEvidence.length === 0 && (
          <p className="mt-6 text-center text-sm text-slate-500">
            No evidence matches the selected filters.
          </p>
        )}

        {/* Load more */}
        {hasMore && (
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => setVisibleCount(prev => prev + 10)}
              className="text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors"
            >
              Load more<span className="ml-1">&rarr;</span>
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
