import { useEffect, useState, useCallback, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useDashboard } from '../hooks/useDashboard';
import { useEvidence } from '../hooks/useEvidence';
import { api } from '../services/api';
import type { Campaign } from '../types';
import { DISPLAY_PHASES, phaseIndex, phaseProgress, daysActive, formatDate } from '../utils/campaign';
import { computeSkillStats } from '../utils/evidence';
import { Card, SectionLabel, Badge, ProgressBar, Button, Input, SkeletonBlock } from '../components/ui';

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function Skeleton() {
  return (
    <div className="space-y-6">
      {/* Identity */}
      <Card className="p-8">
        <SkeletonBlock className="h-2.5 w-36" />
        <SkeletonBlock className="mt-6 h-8 w-72" />
        <div className="mt-3 flex items-center gap-3">
          <SkeletonBlock className="h-5 w-20" />
          <SkeletonBlock className="h-3.5 w-40" />
        </div>
        <div className="mt-8 flex gap-10">
          {[1, 2, 3].map(i => (
            <div key={i}>
              <SkeletonBlock className="h-8 w-10" />
              <SkeletonBlock className="mt-1.5 h-2.5 w-24" />
            </div>
          ))}
        </div>
        <SkeletonBlock className="mt-4 h-2.5 w-44" />
      </Card>

      {/* Skills */}
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-28" />
        <div className="mt-5 flex flex-wrap gap-2.5">
          {[80, 108, 64, 92, 120, 72].map((w, i) => (
            <SkeletonBlock
              key={i}
              className="h-8"
              style={{ width: `${w}px` } as React.CSSProperties}
            />
          ))}
        </div>
      </Card>

      {/* Campaign */}
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-36" />
        <div className="mt-5 flex items-center gap-6">
          <SkeletonBlock className="h-3 w-20" />
          <SkeletonBlock className="h-px w-8" />
          <SkeletonBlock className="h-3 w-16" />
          <SkeletonBlock className="h-px w-8" />
          <SkeletonBlock className="h-3 w-14" />
        </div>
        <SkeletonBlock className="mt-3 h-1 w-full" />
        <SkeletonBlock className="mt-6 h-5 w-56" />
        <SkeletonBlock className="mt-4 h-3 w-44" />
      </Card>
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
      <p className="text-sm font-medium text-neutral-900">Unable to load profile</p>
      <p className="mt-1.5 text-sm text-neutral-500">{message}</p>
      <Button onClick={onRetry} className="mt-6">
        Retry
      </Button>
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
    <Card className="p-8">
      <SectionLabel>Transition Profile</SectionLabel>

      <p className="mt-5 text-2xl font-semibold tracking-tight text-neutral-900">
        {campaign.targetRole}
      </p>

      <div className="mt-2.5 flex flex-wrap items-center gap-3">
        <Badge variant="primary">
          {DISPLAY_PHASES[idx]}
        </Badge>
        <span className="text-sm text-neutral-400">{username}</span>
      </div>

      <div className="mt-8 grid grid-cols-3 gap-4">
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-3xl font-medium font-mono tabular-nums">{days}</p>
          <p className="mt-0.5 text-xs text-neutral-500">days active</p>
        </div>
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-3xl font-medium font-mono tabular-nums">
            {stats.missionsCompleted}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">missions completed</p>
        </div>
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-3xl font-medium font-mono tabular-nums">
            {stats.evidenceCount}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">evidence items</p>
        </div>
      </div>

      <p className="mt-4 text-xs text-neutral-400">
        Campaign started {formatDate(campaign.startDate)}
      </p>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Section 2: Skills Inventory
// ---------------------------------------------------------------------------

function SkillsInventory({ skills }: { skills: string[] }) {
  return (
    <Card className="p-6">
      <SectionLabel>Skills in Focus</SectionLabel>

      {skills.length > 0 ? (
        <div className="mt-5 flex flex-wrap gap-2.5">
          {skills.map(skill => (
            <span
              key={skill}
              className="rounded-[var(--radius-badge)] bg-neutral-100 px-3 py-1.5 text-sm text-neutral-700"
            >
              {skill}
            </span>
          ))}
        </div>
      ) : (
        <div className="mt-5">
          <p className="text-sm leading-relaxed text-neutral-500">
            Skills will be populated as you complete missions and build your
            evidence portfolio.
          </p>
          <div className="mt-4">
            <Link
              to="/missions"
              className="text-sm font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
            >
              Go to missions
              <span className="ml-1">&rarr;</span>
            </Link>
          </div>
        </div>
      )}
    </Card>
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
    <Card className="p-6">
      <SectionLabel>Campaign Journey</SectionLabel>

      {/* Phase indicator */}
      <div className="mt-4 flex items-center">
        {DISPLAY_PHASES.map((phase, i) => (
          <div key={phase} className="flex items-center">
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
            {i < DISPLAY_PHASES.length - 1 && (
              <span
                className={`mx-3 inline-block h-px w-6 sm:w-10 ${
                  i < idx ? 'bg-neutral-400' : 'bg-neutral-200'
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <ProgressBar value={progress} className="mt-3" />

      {/* Trajectory */}
      <p className="mt-6 text-lg font-semibold text-neutral-900">
        {campaign.targetRole}
      </p>
      <p className="mt-1 text-xs text-neutral-400">
        Started {formatDate(campaign.startDate)} &middot;{' '}
        <span className="font-mono tabular-nums">{days}</span> days active
      </p>

      {/* Focus skills with accent */}
      {campaign.skillsFocus.length > 0 && (
        <div className="mt-5 border-t border-neutral-100 pt-5">
          <p className="text-xs text-neutral-400">Campaign skill focus</p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {campaign.skillsFocus.map(skill => (
              <Badge key={skill} variant="primary">
                {skill}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6">
        <Link
          to="/dashboard"
          className="text-sm font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
        >
          View full campaign details
          <span className="ml-1">&rarr;</span>
        </Link>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Section 3.5: Skill Development Chart
// ---------------------------------------------------------------------------

function SkillDevelopmentChart() {
  const { evidence, loading, fetchEvidence } = useEvidence();

  useEffect(() => {
    void fetchEvidence();
  }, [fetchEvidence]);

  const skillStats = useMemo(() => computeSkillStats(evidence), [evidence]);
  const topSkills = skillStats.slice(0, 8);

  if (loading && evidence.length === 0) {
    return (
      <Card className="p-6">
        <SectionLabel>Skill Development</SectionLabel>
        <div className="mt-5 space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="flex items-center gap-4">
              <SkeletonBlock className="h-3 w-24" />
              <SkeletonBlock className="h-1.5 flex-1" />
              <SkeletonBlock className="h-3 w-6" />
            </div>
          ))}
        </div>
      </Card>
    );
  }

  if (evidence.length === 0) {
    return (
      <Card className="p-6">
        <SectionLabel>Skill Development</SectionLabel>
        <div className="mt-5">
          <p className="text-sm leading-relaxed text-neutral-500">
            Complete missions to start tracking skill development. Each piece
            of evidence strengthens your demonstrated capabilities.
          </p>
          <div className="mt-4">
            <Link
              to="/missions"
              className="text-sm font-medium text-neutral-600 hover:text-neutral-900 transition-colors"
            >
              Go to missions
              <span className="ml-1">&rarr;</span>
            </Link>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-6">
      <SectionLabel>Skill Development</SectionLabel>

      <div className="mt-5 space-y-3">
        {topSkills.map((stat, i) => {
          let barClass = 'bg-primary-500/20';
          if (stat.count >= 5) barClass = 'bg-primary-500';
          else if (stat.count >= 3) barClass = 'bg-primary-500/50';

          return (
            <div
              key={stat.skill}
              className="flex items-center gap-4 animate-fade-in-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <span className="w-32 shrink-0 truncate text-sm text-neutral-600">
                {stat.skill}
              </span>
              <ProgressBar
                value={Math.max(stat.ratio * 100, 4)}
                className="flex-1"
                barClassName={barClass}
              />
              <span className="w-6 text-right text-xs font-mono tabular-nums text-neutral-400">
                {stat.count}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4">
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-3xl font-medium font-mono tabular-nums">
            {evidence.length}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">total evidence</p>
        </div>
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-3xl font-medium font-mono tabular-nums">
            {skillStats.length}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">skills covered</p>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Section 4: Delete Account
// ---------------------------------------------------------------------------

function DeleteAccount({
  getToken,
  signOut,
}: {
  getToken: () => Promise<string>;
  signOut: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const handleDelete = useCallback(async () => {
    if (confirmText !== 'DELETE') return;
    setDeleting(true);
    setDeleteError('');
    try {
      const token = await getToken();
      await api.profile.delete(token);
      await signOut();
      navigate('/login');
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : 'Failed to delete account',
      );
    } finally {
      setDeleting(false);
    }
  }, [confirmText, getToken, signOut, navigate]);

  return (
    <Card className="p-6">
      <SectionLabel>Account</SectionLabel>

      <div className="mt-5 border-t border-neutral-100 pt-5">
        <p className="text-sm font-medium text-neutral-900">Delete account</p>
        <p className="mt-1.5 text-sm leading-relaxed text-neutral-500">
          This will permanently delete your account and all associated data
          including your profile, campaigns, missions, and evidence vault.
          This action cannot be undone.
        </p>

        {deleteError && (
          <p className="mt-3 text-sm text-error-600">{deleteError}</p>
        )}

        {!showConfirm ? (
          <button
            onClick={() => setShowConfirm(true)}
            className="mt-4 text-sm font-medium text-error-600 hover:text-error-700 transition-colors"
          >
            Delete my account
          </button>
        ) : (
          <div className="mt-4 space-y-3">
            <Input
              label="Type DELETE to confirm"
              placeholder="DELETE"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              autoComplete="off"
            />
            <div className="flex items-center gap-3">
              <Button
                variant="destructive"
                size="sm"
                disabled={confirmText !== 'DELETE' || deleting}
                onClick={() => void handleDelete()}
              >
                {deleting ? 'Deleting...' : 'Confirm deletion'}
              </Button>
              <button
                onClick={() => {
                  setShowConfirm(false);
                  setConfirmText('');
                  setDeleteError('');
                }}
                className="text-sm text-neutral-500 hover:text-neutral-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function Profile() {
  const { user, getToken, signOut } = useAuth();
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

  if (!campaign) {
    return (
      <div className="space-y-6 animate-fade-in">
        <Card className="p-8 text-center">
          <p className="text-sm text-neutral-500">
            Complete onboarding to set up your profile.
          </p>
        </Card>
        <DeleteAccount getToken={getToken} signOut={signOut} />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <IdentitySummary
        username={user?.username ?? ''}
        campaign={campaign}
        stats={stats}
      />

      <SkillsInventory skills={campaign.skillsFocus} />

      <SkillDevelopmentChart />

      <CampaignJourney campaign={campaign} />

      <DeleteAccount getToken={getToken} signOut={signOut} />
    </div>
  );
}
