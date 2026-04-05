import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useImpactScore } from '../hooks/useImpactScore';
import { useAuth } from '../hooks/useAuth';
import { api } from '../services/api';
import { Card, Button, SkeletonBlock, SectionLabel } from '../components/ui';
import CRIGauge from '../components/score/CRIGauge';
import CRIBreakdown from '../components/score/CRIBreakdown';
import DimensionTile from '../components/score/DimensionTile';
import PhaseTrack from '../components/score/PhaseTrack';
import SkillConstellation from '../components/score/SkillConstellation';
import MarketAlignmentRadar from '../components/score/MarketAlignmentRadar';
import DifficultyTrajectory from '../components/score/DifficultyTrajectory';
import ScoreExportBar from '../components/score/ScoreExportBar';

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function Skeleton() {
  return (
    <div className="space-y-6">
      {/* CRI gauge */}
      <Card className="flex flex-col items-center p-8">
        <SkeletonBlock className="h-[240px] w-[240px] rounded-full" />
        <SkeletonBlock className="mt-3 h-3 w-48" />
      </Card>
      {/* Phase track */}
      <Card className="p-6">
        <SkeletonBlock className="h-3 w-full" />
      </Card>
      {/* Dimension tiles */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {[1, 2, 3, 4, 5].map(i => (
          <div key={i} className="rounded-[var(--radius-card)] border border-neutral-100 p-4">
            <SkeletonBlock className="h-2.5 w-20" />
            <SkeletonBlock className="mt-3 h-6 w-12" />
          </div>
        ))}
      </div>
      {/* Charts */}
      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-6"><SkeletonBlock className="h-[300px] w-full" /></Card>
        <Card className="p-6"><SkeletonBlock className="h-[300px] w-full" /></Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state (day 1)
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="space-y-6 animate-fade-in">
      <Card variant="elevated" className="p-10 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-surface-3">
          <svg className="h-8 w-8 text-primary-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
          </svg>
        </div>
        <h2 className="mt-5 text-lg font-semibold text-neutral-900">
          Your scorecard starts here
        </h2>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-neutral-500">
          Your Career Readiness Score is built from what you do, not what you say.
          Complete your first 3 missions to unlock your score.
        </p>
        <div className="section-divider mx-auto mt-6 w-32" />
        <div className="mt-6">
          <Link to="/missions">
            <Button size="lg">Start your first mission</Button>
          </Link>
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

function ScorecardError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <p className="text-sm font-medium text-neutral-900">Unable to load scorecard</p>
      <p className="mt-1.5 text-sm text-neutral-500">{message}</p>
      <Button onClick={onRetry} className="mt-6">Retry</Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ImpactScorecardPage() {
  const { data, loading, error, fetchScore } = useImpactScore();
  const { getToken } = useAuth();
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [showExport, setShowExport] = useState(false);

  useEffect(() => {
    void fetchScore();
  }, [fetchScore]);

  // Show export bar after scrolling past the gauge
  useEffect(() => {
    function onScroll() {
      setShowExport(window.scrollY > 300);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const handleExportPdf = useCallback(async () => {
    const token = await getToken();
    const result = await api.score.exportPdf(token);
    return result.url;
  }, [getToken]);

  const handleShare = useCallback(async () => {
    const token = await getToken();
    const result = await api.score.share(token);
    return result.url;
  }, [getToken]);

  // Loading
  if (loading || (!data && !error)) {
    return (
      <div className="animate-fade-in">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Impact Scorecard</h1>
          <p className="mt-1 text-sm text-neutral-500">Your evidence-backed career readiness score</p>
        </div>
        <Skeleton />
      </div>
    );
  }

  // Error
  if (error) {
    return (
      <div>
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Impact Scorecard</h1>
          <p className="mt-1 text-sm text-neutral-500">Your evidence-backed career readiness score</p>
        </div>
        <ScorecardError message={error} onRetry={() => void fetchScore()} />
      </div>
    );
  }

  if (!data) return null;

  // Empty state: fewer than 3 missions completed
  if (data.missionsCompleted < 3) {
    return (
      <div>
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Impact Scorecard</h1>
          <p className="mt-1 text-sm text-neutral-500">Your evidence-backed career readiness score</p>
        </div>
        <EmptyState />
      </div>
    );
  }

  const d = data.dimensionDetail;

  // Determine trends from detail
  const velTrend: 'up' | 'down' | 'flat' =
    d.missionVelocity.velocityTrend > 0.1 ? 'up' : d.missionVelocity.velocityTrend < -0.1 ? 'down' : 'flat';

  // Build target/user skill vectors for radar
  const targetSkills: Record<string, number> = {};
  const userSkills: Record<string, number> = {};
  if (d.marketAlignment.hotSkillsGap) {
    for (const gap of d.marketAlignment.hotSkillsGap) {
      targetSkills[gap.skill] = gap.demand;
    }
  }
  for (const sk of d.evidenceDensity.skillDetail) {
    userSkills[sk.skill.toLowerCase()] = sk.count;
    if (!targetSkills[sk.skill.toLowerCase()]) {
      targetSkills[sk.skill.toLowerCase()] = 0.5;
    }
  }

  return (
    <div className="space-y-6 animate-fade-in pb-24">
      {/* Page header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Impact Scorecard</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Your evidence-backed career readiness score
            {data.targetRole && <> for <span className="font-medium text-neutral-700">{data.targetRole}</span></>}
          </p>
        </div>
        <p className="text-xs font-mono tabular-nums text-neutral-400">
          Updated {new Date(data.computedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
        </p>
      </div>

      {/* CRI Gauge — hero */}
      <Card variant="elevated" className="py-8 px-6">
        <CRIGauge
          score={data.cri}
          evidenceCount={data.evidenceCount}
          onClick={() => setBreakdownOpen(true)}
        />
      </Card>

      {/* Phase Track */}
      <Card className="p-6">
        <SectionLabel>Campaign Phase</SectionLabel>
        <div className="mt-4">
          <PhaseTrack
            currentPhase={d.phaseProgression.phase}
            gatesMet={d.phaseProgression.gatesMet}
            startDate={d.phaseProgression.startDate}
          />
        </div>
      </Card>

      {/* Dimension tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <DimensionTile
          name="Velocity"
          score={data.missionVelocityScore}
          trend={velTrend}
          delay={100}
        />
        <DimensionTile
          name="Evidence"
          score={data.evidenceDensityScore}
          trend={d.evidenceDensity.totalEntries > 5 ? 'up' : 'flat'}
          delay={150}
        />
        <DimensionTile
          name="Market Fit"
          score={data.marketAlignmentScore}
          trend={d.marketAlignment.hasMarketData ? 'flat' : 'flat'}
          delay={200}
        />
        <DimensionTile
          name="Phase"
          score={data.phaseProgressionScore}
          trend="flat"
          delay={250}
        />
        <DimensionTile
          name="Difficulty"
          score={data.adaptiveDifficultyScore}
          trend={d.adaptiveDifficulty.peak_difficulty_avg >= 3 ? 'up' : 'flat'}
          delay={300}
        />
      </div>

      {/* Two-column: Constellation + Radar */}
      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-6">
          <SkillConstellation skills={d.evidenceDensity.skillDetail} />
        </Card>
        <Card className="p-6">
          <MarketAlignmentRadar
            targetSkills={targetSkills}
            userSkills={userSkills}
            hotSkillsGap={d.marketAlignment.hotSkillsGap}
            matchedSkills={d.marketAlignment.matchedSkills}
            totalTargetSkills={d.marketAlignment.totalTargetSkills}
            targetRole={d.marketAlignment.targetRole || data.targetRole}
          />
        </Card>
      </div>

      {/* Difficulty Trajectory */}
      <Card className="p-6">
        <DifficultyTrajectory
          historyByCategory={d.adaptiveDifficulty.historyByCategory || {}}
          difficultyCeilings={d.adaptiveDifficulty.difficultyCeilings}
        />
      </Card>

      {/* Footer note */}
      <p className="text-center text-xs text-neutral-400 tracking-wide">
        This score is computed from timestamped activity data. REGAIN does not issue scores based on self-reported surveys.
      </p>

      {/* CRI Breakdown Modal */}
      <CRIBreakdown
        open={breakdownOpen}
        onClose={() => setBreakdownOpen(false)}
        cri={data.cri}
        dimensions={{
          missionVelocityScore: data.missionVelocityScore,
          evidenceDensityScore: data.evidenceDensityScore,
          marketAlignmentScore: data.marketAlignmentScore,
          phaseProgressionScore: data.phaseProgressionScore,
          adaptiveDifficultyScore: data.adaptiveDifficultyScore,
        }}
        detail={d}
        evidenceCount={data.evidenceCount}
        missionsCompleted={data.missionsCompleted}
      />

      {/* Export bar */}
      <ScoreExportBar
        onExportPdf={handleExportPdf}
        onShare={handleShare}
        visible={showExport}
      />
    </div>
  );
}
