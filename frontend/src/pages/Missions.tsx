import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useMissions } from '../hooks/useMissions';
import type { Mission, CompleteData } from '../types';
import { Card, SectionLabel, Button, Badge, SkeletonBlock } from '../components/ui';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
    <div className="space-y-6">
      {/* Primary mission card */}
      <Card className="p-8">
        <SkeletonBlock className="h-2.5 w-28" />
        <SkeletonBlock className="mt-5 h-7 w-72" />
        <SkeletonBlock className="mt-4 h-3.5 w-full" />
        <SkeletonBlock className="mt-2 h-3.5 w-4/5" />
        <div className="mt-8 border-t border-neutral-100 pt-6">
          <SkeletonBlock className="h-2.5 w-20" />
          <SkeletonBlock className="mt-3 h-24 w-full" />
          <SkeletonBlock className="mt-4 h-2.5 w-32" />
          <SkeletonBlock className="mt-3 h-10 w-full" />
          <SkeletonBlock className="mt-6 h-10 w-40" />
        </div>
      </Card>

      {/* Alternate missions */}
      <div>
        <SkeletonBlock className="h-2.5 w-32" />
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2].map(i => (
            <Card key={i} className="p-5">
              <SkeletonBlock className="h-4 w-48" />
              <SkeletonBlock className="mt-3 h-3 w-full" />
              <SkeletonBlock className="mt-1.5 h-3 w-2/3" />
              <SkeletonBlock className="mt-4 h-3 w-28" />
            </Card>
          ))}
        </div>
      </div>

      {/* Mission history */}
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-28" />
        <div className="mt-5 space-y-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="flex items-center gap-4">
              <SkeletonBlock className="h-3.5 flex-1" />
              <SkeletonBlock className="h-3 w-16" />
              <SkeletonBlock className="h-3 w-20" />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

function MissionsError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <p className="text-sm font-medium text-neutral-900">Unable to load missions</p>
      <p className="mt-1.5 text-sm text-neutral-500">{message}</p>
      <Button onClick={onRetry} className="mt-6">
        Retry
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function AllCaughtUp() {
  return (
    <Card className="p-8">
      <div className="flex flex-col items-center py-12 text-center">
        <p className="text-xl font-semibold text-neutral-900">All caught up</p>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-500">
          Your next mission arrives tomorrow. In the meantime, review your
          evidence or check your dashboard.
        </p>
        <div className="mt-6 flex gap-6">
          <Link
            to="/evidence"
            className="text-sm font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
          >
            View evidence<span className="ml-1">&rarr;</span>
          </Link>
          <Link
            to="/dashboard"
            className="text-sm font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
          >
            Dashboard<span className="ml-1">&rarr;</span>
          </Link>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Completion confirmation
// ---------------------------------------------------------------------------

function CompletionConfirmation({ evidenceId }: { evidenceId: string }) {
  return (
    <Card variant="accent" className="p-8 animate-scale-in">
      <div className="flex flex-col items-center py-8 text-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-50">
          <svg
            className="h-5 w-5 text-primary-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4.5 12.75l6 6 9-13.5"
            />
          </svg>
        </div>
        <p className="mt-4 text-lg font-semibold text-neutral-900">
          Mission complete
        </p>
        <p className="mt-1.5 text-sm text-neutral-500">
          Your reflection has been recorded as evidence.
        </p>
        <p className="mt-3 text-xs font-mono tabular-nums text-neutral-400">
          {evidenceId}
        </p>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Completion form
// ---------------------------------------------------------------------------

function CompletionForm({
  missionId,
  onComplete,
  onSkip,
  completing,
  completionError,
}: {
  missionId: string;
  onComplete: (missionId: string, data: CompleteData) => void;
  onSkip: (missionId: string) => void;
  completing: boolean;
  completionError: string | null;
}) {
  const [reflection, setReflection] = useState('');
  const [artifactUrl, setArtifactUrl] = useState('');
  const [skillTags, setSkillTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  function addTag(tag: string) {
    const trimmed = tag.trim();
    if (trimmed && !skillTags.includes(trimmed)) {
      setSkillTags(prev => [...prev, trimmed]);
    }
    setTagInput('');
  }

  function removeTag(tag: string) {
    setSkillTags(prev => prev.filter(t => t !== tag));
  }

  function handleSubmit() {
    if (!reflection.trim()) {
      setValidationError('Share what you did before completing.');
      return;
    }
    setValidationError(null);
    onComplete(missionId, {
      reflection: reflection.trim(),
      artifactUrl: artifactUrl.trim() || undefined,
      skillTags,
    });
  }

  return (
    <div className="mt-8 border-t border-neutral-100 pt-6">
      {/* Reflection */}
      <label className="block">
        <span className="text-xs font-medium text-neutral-500">
          Your reflection
        </span>
        <textarea
          value={reflection}
          onChange={e => {
            setReflection(e.target.value);
            if (validationError) setValidationError(null);
          }}
          placeholder="Describe what you did and what you learned..."
          rows={4}
          className="mt-2 block w-full resize-y rounded-[var(--radius-button)] border border-neutral-200 bg-white px-4 py-3 text-sm leading-relaxed text-neutral-900 placeholder:text-neutral-300 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 transition-shadow"
        />
      </label>

      {validationError && (
        <p className="mt-2 text-xs text-error-600">{validationError}</p>
      )}

      {/* Artifact URL */}
      <label className="mt-4 block">
        <span className="text-xs font-medium text-neutral-500">
          Link to artifact (optional)
        </span>
        <input
          type="url"
          value={artifactUrl}
          onChange={e => setArtifactUrl(e.target.value)}
          placeholder="https://"
          className="mt-2 block w-full rounded-[var(--radius-button)] border border-neutral-200 bg-white px-4 py-2.5 text-sm text-neutral-900 placeholder:text-neutral-300 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 transition-shadow"
        />
      </label>

      {/* Skill tags */}
      <div className="mt-4">
        <span className="text-xs font-medium text-neutral-500">Skill tags</span>
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-[var(--radius-button)] border border-neutral-200 bg-white px-3 py-2">
          {skillTags.map(tag => (
            <span
              key={tag}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-badge)] bg-neutral-100 px-2.5 py-1 text-xs text-neutral-600"
            >
              {tag}
              <button
                type="button"
                onClick={() => removeTag(tag)}
                className="text-neutral-400 hover:text-neutral-600 transition-colors"
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
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </span>
          ))}
          <input
            type="text"
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addTag(tagInput);
              }
            }}
            placeholder={
              skillTags.length === 0
                ? 'Type a skill and press Enter'
                : 'Add more...'
            }
            className="min-w-[120px] flex-1 border-0 bg-transparent py-1 text-xs text-neutral-900 placeholder:text-neutral-300 focus:outline-none"
          />
        </div>
      </div>

      {completionError && (
        <p className="mt-4 text-xs text-error-600">{completionError}</p>
      )}

      {/* Actions */}
      <div className="mt-6 flex items-center gap-6">
        <Button onClick={handleSubmit} disabled={completing}>
          {completing ? 'Completing...' : 'Complete Mission'}
        </Button>
        <button
          type="button"
          onClick={() => onSkip(missionId)}
          disabled={completing}
          className="text-xs text-neutral-400 hover:underline disabled:opacity-50"
        >
          Skip this mission
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Primary mission card
// ---------------------------------------------------------------------------

function PrimaryMissionCard({
  mission,
  onComplete,
  onSkip,
  completing,
  completionError,
}: {
  mission: Mission;
  onComplete: (missionId: string, data: CompleteData) => void;
  onSkip: (missionId: string) => void;
  completing: boolean;
  completionError: string | null;
}) {
  return (
    <Card variant="accent" className="p-8">
      <SectionLabel>Current Mission</SectionLabel>

      <h2 className="mt-4 text-2xl font-semibold tracking-tight text-neutral-900">
        {mission.title}
      </h2>

      <p className="mt-3 text-sm leading-relaxed text-neutral-500">
        {mission.description}
      </p>

      <CompletionForm
        key={mission.missionId}
        missionId={mission.missionId}
        onComplete={onComplete}
        onSkip={onSkip}
        completing={completing}
        completionError={completionError}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Alternate missions
// ---------------------------------------------------------------------------

function AlternateMissionCard({
  mission,
  onSwitch,
  index,
}: {
  mission: Mission;
  onSwitch: (missionId: string) => void;
  index: number;
}) {
  return (
    <Card hoverable className="p-5 animate-fade-in-up" style={{ animationDelay: `${index * 60}ms` }}>
      <h3 className="text-sm font-medium text-neutral-900 line-clamp-2">
        {mission.title}
      </h3>
      <p className="mt-2 text-xs leading-relaxed text-neutral-500 line-clamp-2">
        {mission.description}
      </p>
      <button
        type="button"
        onClick={() => onSwitch(mission.missionId)}
        className="mt-4 text-xs font-medium text-neutral-500 hover:text-neutral-700 transition-colors"
      >
        Switch to this mission<span className="ml-1">&rarr;</span>
      </button>
    </Card>
  );
}

function AlternateMissions({
  missions,
  onSwitch,
}: {
  missions: Mission[];
  onSwitch: (missionId: string) => void;
}) {
  if (missions.length === 0) return null;

  return (
    <section>
      <SectionLabel>Alternate Missions</SectionLabel>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {missions.slice(0, 3).map((m, i) => (
          <AlternateMissionCard
            key={m.missionId}
            mission={m}
            onSwitch={onSwitch}
            index={i}
          />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Mission history
// ---------------------------------------------------------------------------

function MissionHistoryItem({ mission }: { mission: Mission }) {
  const [expanded, setExpanded] = useState(false);
  const isCompleted = mission.status === 'completed';

  return (
    <div className="border-b border-neutral-100 last:border-0">
      <button
        type="button"
        onClick={() => setExpanded(prev => !prev)}
        className="flex w-full items-center gap-4 py-3 text-left"
      >
        <span className="flex-1 truncate text-sm text-neutral-700">
          {mission.title}
        </span>
        <Badge variant={isCompleted ? 'primary' : 'default'}>
          {isCompleted ? 'Completed' : 'Skipped'}
        </Badge>
        {mission.completedDate && (
          <span className="shrink-0 text-xs font-mono tabular-nums text-neutral-400">
            {formatDate(mission.completedDate)}
          </span>
        )}
        <svg
          className={`h-3 w-3 shrink-0 text-neutral-300 transition-transform ${
            expanded ? 'rotate-180' : ''
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19.5 8.25l-7.5 7.5-7.5-7.5"
          />
        </svg>
      </button>
      {expanded && (
        <div className="pb-3">
          <p className="text-xs leading-relaxed text-neutral-500">
            {mission.description}
          </p>
        </div>
      )}
    </div>
  );
}

function MissionHistory({
  missions,
  showAll,
  onShowMore,
}: {
  missions: Mission[];
  showAll: boolean;
  onShowMore: () => void;
}) {
  if (missions.length === 0) {
    return (
      <Card className="p-6">
        <SectionLabel>Mission History</SectionLabel>
        <p className="mt-4 text-sm leading-relaxed text-neutral-500">
          Your mission history will appear here as you complete missions.
        </p>
      </Card>
    );
  }

  const visible = showAll ? missions : missions.slice(0, 10);

  return (
    <Card className="p-6">
      <SectionLabel>Mission History</SectionLabel>
      <div className="mt-4">
        {visible.map(m => (
          <MissionHistoryItem key={m.missionId} mission={m} />
        ))}
      </div>
      {!showAll && missions.length > 10 && (
        <button
          type="button"
          onClick={onShowMore}
          className="mt-4 text-xs font-medium text-neutral-500 hover:text-neutral-700 transition-colors"
        >
          View more<span className="ml-1">&rarr;</span>
        </button>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function Missions() {
  const { missions, loading, error, fetchMissions, completeMission } =
    useMissions();

  const [completing, setCompleting] = useState(false);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const [completedResult, setCompletedResult] = useState<{
    missionId: string;
    evidenceId: string;
  } | null>(null);
  const [skippedIds, setSkippedIds] = useState<Set<string>>(new Set());
  const [primaryOverride, setPrimaryOverride] = useState<string | null>(null);
  const [showAllHistory, setShowAllHistory] = useState(false);

  useEffect(() => {
    void fetchMissions();
  }, [fetchMissions]);

  // Derive mission categories from flat list
  const activeMissions = missions.filter(
    m =>
      (m.status === 'pending' || m.status === 'in_progress') &&
      !skippedIds.has(m.missionId),
  );

  const historyMissions = missions
    .filter(m => m.status === 'completed' || m.status === 'skipped')
    .sort((a, b) => {
      if (a.completedDate && b.completedDate) {
        return (
          new Date(b.completedDate).getTime() -
          new Date(a.completedDate).getTime()
        );
      }
      if (a.completedDate) return -1;
      if (b.completedDate) return 1;
      return 0;
    });

  // Primary = overridden selection or first active
  let primaryMission: Mission | null = null;
  let alternateMissions: Mission[] = [];

  if (activeMissions.length > 0) {
    if (
      primaryOverride &&
      activeMissions.some(m => m.missionId === primaryOverride)
    ) {
      primaryMission =
        activeMissions.find(m => m.missionId === primaryOverride) ?? null;
      alternateMissions = activeMissions.filter(
        m => m.missionId !== primaryOverride,
      );
    } else {
      primaryMission = activeMissions[0];
      alternateMissions = activeMissions.slice(1);
    }
  }

  const handleComplete = useCallback(
    async (missionId: string, data: CompleteData) => {
      setCompleting(true);
      setCompletionError(null);
      const result = await completeMission(missionId, data);
      setCompleting(false);

      if (result) {
        setCompletedResult({ missionId, evidenceId: result.evidenceId });
        setPrimaryOverride(null);
        setTimeout(() => {
          setCompletedResult(null);
          void fetchMissions();
        }, 2000);
      } else {
        setCompletionError(
          'Something went wrong. Your text is safe — try again.',
        );
      }
    },
    [completeMission, fetchMissions],
  );

  const handleSkip = useCallback((missionId: string) => {
    setSkippedIds(prev => new Set(prev).add(missionId));
    setPrimaryOverride(null);
  }, []);

  const handleSwitch = useCallback((missionId: string) => {
    setPrimaryOverride(missionId);
  }, []);

  // Loading state (only when no missions loaded yet)
  if (loading && missions.length === 0) {
    return <Skeleton />;
  }

  // Error state (only when no missions loaded yet)
  if (error && missions.length === 0) {
    return (
      <MissionsError message={error} onRetry={() => void fetchMissions()} />
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Section 1: Primary mission or completion confirmation or empty state */}
      {completedResult ? (
        <CompletionConfirmation evidenceId={completedResult.evidenceId} />
      ) : primaryMission ? (
        <PrimaryMissionCard
          mission={primaryMission}
          onComplete={handleComplete}
          onSkip={handleSkip}
          completing={completing}
          completionError={completionError}
        />
      ) : (
        <AllCaughtUp />
      )}

      {/* Section 2: Alternate missions (omitted entirely if none) */}
      {!completedResult && (
        <AlternateMissions
          missions={alternateMissions}
          onSwitch={handleSwitch}
        />
      )}

      {/* Section 3: Mission history */}
      <MissionHistory
        missions={historyMissions}
        showAll={showAllHistory}
        onShowMore={() => setShowAllHistory(true)}
      />
    </div>
  );
}
