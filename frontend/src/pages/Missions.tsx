import { useEffect, useState, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useMissions } from '../hooks/useMissions';
import { useDashboard } from '../hooks/useDashboard';
import { useMutationBus } from '../hooks/useMutationBus';
import { useAuth } from '../hooks/useAuth';
import { api } from '../services/api';
import type { Mission, CompleteData } from '../types';
import { Card, SectionLabel, Button, Badge, SkeletonBlock, useToast } from '../components/ui';

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
// Empty state — smart: generate more or show limit reached
// ---------------------------------------------------------------------------

function AllCaughtUp({
  dailyRemaining,
  dailyLimit,
  generating,
  generateError,
  onGenerate,
}: {
  dailyRemaining: number | null;
  dailyLimit: number | null;
  generating: boolean;
  generateError: string | null;
  onGenerate: () => void;
}) {
  const canGenerate = dailyRemaining !== null && dailyRemaining > 0;
  const limitReached = dailyRemaining !== null && dailyRemaining <= 0;

  return (
    <Card className="p-8">
      <div className="flex flex-col items-center py-12 text-center">
        <p className="text-xl font-semibold text-neutral-900">All caught up</p>

        {canGenerate && (
          <>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-500">
              Ready for more? Generate a new mission to keep building momentum.
            </p>
            {generateError && (
              <p className="mt-3 text-sm text-error-600">{generateError}</p>
            )}
            <Button
              onClick={onGenerate}
              disabled={generating}
              className="mt-6"
            >
              {generating ? 'Generating...' : 'Generate New Mission'}
            </Button>
            <p className="mt-3 text-xs text-neutral-400">
              {dailyRemaining} of {dailyLimit ?? dailyRemaining} remaining today
            </p>
          </>
        )}

        {limitReached && (
          <>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-500">
              You've reached today's mission limit. New missions will be
              available after midnight UTC.
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
          </>
        )}

        {dailyRemaining === null && (
          <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-500">
            Check back soon for new missions.
          </p>
        )}
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
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-success-50 ring-4 ring-success-100">
          <svg
            className="h-6 w-6 text-success-600"
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
        <div className="section-divider mx-auto mt-4 w-24" />
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
  const { getToken } = useAuth();
  const [reflection, setReflection] = useState('');
  const [artifactUrl, setArtifactUrl] = useState('');
  const [skillTags, setSkillTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const fetchSuggestions = useCallback(async (text: string) => {
    if (text.trim().length < 20) return;
    try {
      const token = await getToken();
      const result = await api.evidence.suggestTags(text, token);
      // Filter out already-selected tags.
      setSuggestions(result.suggestions.filter(s => !skillTags.includes(s)));
    } catch {
      // Silently fail — suggestions are non-critical.
    }
  }, [getToken, skillTags]);

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
          onBlur={() => void fetchSuggestions(reflection)}
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
        {suggestions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {suggestions.map(tag => (
              <button
                key={tag}
                type="button"
                onClick={() => {
                  addTag(tag);
                  setSuggestions(prev => prev.filter(s => s !== tag));
                }}
                className="inline-flex items-center gap-1 rounded-[var(--radius-badge)] bg-accent-50 px-2.5 py-1 text-xs text-accent-600 hover:bg-accent-100 transition-colors"
              >
                <span>+</span>
                {tag}
              </button>
            ))}
          </div>
        )}
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
          className="px-3 py-2 text-xs text-neutral-400 hover:text-neutral-500 hover:bg-neutral-50 rounded-[var(--radius-button)] transition-colors duration-150 disabled:opacity-50"
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

// ---------------------------------------------------------------------------
// Day-change detection helper
// ---------------------------------------------------------------------------

function getUtcDate(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function Missions() {
  const {
    missions,
    dailyRemaining,
    dailyLimit,
    loading,
    error,
    fetchMissions,
    completeMission,
    generateMission,
  } = useMissions();

  const { data: dashboardData, loading: dashLoading, fetchDashboard } = useDashboard();
  const { emit } = useMutationBus();

  const [completing, setCompleting] = useState(false);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const [completedResult, setCompletedResult] = useState<{
    missionId: string;
    evidenceId: string;
  } | null>(null);
  const [skippedIds, setSkippedIds] = useState<Set<string>>(new Set());
  const [primaryOverride, setPrimaryOverride] = useState<string | null>(null);
  const [showAllHistory, setShowAllHistory] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Track the UTC date when the page was last fetched.
  const lastDateRef = useRef(getUtcDate());

  useEffect(() => {
    void fetchDashboard();
    void fetchMissions();
  }, [fetchDashboard, fetchMissions]);

  // Day-change detection: visibility change + 60s interval.
  useEffect(() => {
    function checkDayChange() {
      const today = getUtcDate();
      if (today !== lastDateRef.current) {
        lastDateRef.current = today;
        void fetchMissions();
      }
    }

    function handleVisibility() {
      if (document.visibilityState === 'visible') {
        checkDayChange();
      }
    }

    document.addEventListener('visibilitychange', handleVisibility);
    const interval = setInterval(checkDayChange, 60_000);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      clearInterval(interval);
    };
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
        emit({ type: 'mission:completed' });
        emit({ type: 'evidence:logged' });
        setCompletedResult({ missionId, evidenceId: result.evidenceId });
        setPrimaryOverride(null);
        setTimeout(() => {
          setCompletedResult(null);
        }, 2000);
      } else {
        setCompletionError(
          'Something went wrong. Your text is safe — try again.',
        );
      }
    },
    [completeMission, emit],
  );

  const { toast } = useToast();

  const handleSkip = useCallback((missionId: string) => {
    setSkippedIds(prev => new Set(prev).add(missionId));
    setPrimaryOverride(null);
    toast({
      message: 'Mission skipped',
      variant: 'default',
      duration: 5000,
      action: {
        label: 'Undo',
        onClick: () => {
          setSkippedIds(prev => {
            const next = new Set(prev);
            next.delete(missionId);
            return next;
          });
        },
      },
    });
  }, [toast]);

  const handleSwitch = useCallback((missionId: string) => {
    setPrimaryOverride(missionId);
  }, []);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setGenerateError(null);
    const result = await generateMission();
    setGenerating(false);
    if (!result) {
      setGenerateError('Could not generate a mission. Try again.');
    }
  }, [generateMission]);

  // Loading state (only when no missions loaded yet)
  if ((loading || dashLoading) && missions.length === 0) {
    return <Skeleton />;
  }

  // Error state (only when no missions loaded yet)
  if (error && missions.length === 0) {
    return (
      <MissionsError message={error} onRetry={() => void fetchMissions()} />
    );
  }

  // No campaign — user needs to complete onboarding first
  if (dashboardData && !dashboardData.campaign) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Missions</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Build evidence through daily challenges
          </p>
        </div>
        <Card className="p-10 text-center">
          <p className="text-xl font-semibold text-neutral-900">
            Complete onboarding to unlock missions
          </p>
          <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-neutral-500">
            Set up your career campaign first. Once your profile and target role are
            configured, you can start generating daily missions tailored to your transition.
          </p>
          <div className="section-divider mx-auto mt-6 w-32" />
          <div className="mt-6">
            <Link to="/onboarding">
              <Button size="lg">Go to Onboarding</Button>
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Missions</h1>
        <p className="mt-1 text-sm text-neutral-500">
          {activeMissions.length > 0
            ? `${activeMissions.length} active mission${activeMissions.length > 1 ? 's' : ''} available`
            : 'Build evidence through daily challenges'}
        </p>
      </div>

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
        <AllCaughtUp
          dailyRemaining={dailyRemaining}
          dailyLimit={dailyLimit}
          generating={generating}
          generateError={generateError}
          onGenerate={() => void handleGenerate()}
        />
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
