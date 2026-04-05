import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Card, SkeletonBlock, Button } from '../components/ui';
import CRIGauge from '../components/score/CRIGauge';
import DimensionTile from '../components/score/DimensionTile';

const API_BASE_URL = import.meta.env.VITE_API_URL;

interface PublicScore {
  cri: number;
  missionVelocityScore: number;
  evidenceDensityScore: number;
  marketAlignmentScore: number;
  phaseProgressionScore: number;
  adaptiveDifficultyScore: number;
  evidenceCount: number;
  missionsCompleted: number;
  targetRole: string;
  computedAt: string;
}

export default function PublicScorecardPage() {
  const { shortCode } = useParams<{ shortCode: string }>();
  const [data, setData] = useState<PublicScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shortCode) return;
    fetch(`${API_BASE_URL}/score/public/${shortCode}`)
      .then(res => {
        if (!res.ok) throw new Error(res.status === 404 ? 'Scorecard not found' : 'Failed to load');
        return res.json();
      })
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, [shortCode]);

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-2 flex items-center justify-center p-6">
        <div className="w-full max-w-lg space-y-6">
          <Card className="p-8 flex flex-col items-center">
            <SkeletonBlock className="h-[200px] w-[200px] rounded-full" />
            <SkeletonBlock className="mt-4 h-3 w-48" />
          </Card>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-surface-2 flex items-center justify-center p-6">
        <Card variant="elevated" className="max-w-sm p-8 text-center">
          <h1 className="text-lg font-semibold text-neutral-900">Scorecard Not Found</h1>
          <p className="mt-2 text-sm text-neutral-500">
            {error || 'This scorecard link may have expired or been removed.'}
          </p>
          <a href="https://regain.altivum.ai" className="mt-6 inline-block">
            <Button variant="secondary" size="sm">Learn about REGAIN</Button>
          </a>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-2">
      {/* Header */}
      <header className="border-b border-neutral-100 bg-surface-1 px-6 py-4">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <img src="/regain-type.png" alt="Regain" className="h-6 w-auto" />
          <span className="text-xs text-neutral-400">Career Readiness Score</span>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-8 space-y-6">
        {/* Target role */}
        {data.targetRole && (
          <p className="text-center text-sm text-neutral-500">
            Target Role: <span className="font-medium text-neutral-700">{data.targetRole}</span>
          </p>
        )}

        {/* CRI Gauge */}
        <Card variant="elevated" className="py-8 px-6">
          <CRIGauge score={data.cri} evidenceCount={data.evidenceCount} />
        </Card>

        {/* Dimension tiles */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <DimensionTile name="Velocity" score={data.missionVelocityScore} trend="flat" delay={100} />
          <DimensionTile name="Evidence" score={data.evidenceDensityScore} trend="flat" delay={150} />
          <DimensionTile name="Market Fit" score={data.marketAlignmentScore} trend="flat" delay={200} />
          <DimensionTile name="Phase" score={data.phaseProgressionScore} trend="flat" delay={250} />
          <DimensionTile name="Difficulty" score={data.adaptiveDifficultyScore} trend="flat" delay={300} />
        </div>

        {/* Stats summary */}
        <Card className="p-6">
          <div className="flex gap-4 text-center">
            <div className="flex-1">
              <p className="text-2xl font-mono tabular-nums font-medium text-neutral-900">{data.missionsCompleted}</p>
              <p className="mt-0.5 text-xs text-neutral-400">Missions Completed</p>
            </div>
            <div className="flex-1">
              <p className="text-2xl font-mono tabular-nums font-medium text-neutral-900">{data.evidenceCount}</p>
              <p className="mt-0.5 text-xs text-neutral-400">Evidence Entries</p>
            </div>
          </div>
        </Card>

        {/* Verification badge */}
        <div className="flex items-center justify-center gap-2 rounded-[var(--radius-card)] border border-success-100 bg-success-50/50 px-4 py-3">
          <svg className="h-4 w-4 text-success-500 shrink-0" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1Zm3.22 4.72a.75.75 0 0 0-1.06-1.06L7 7.82 5.84 6.66a.75.75 0 0 0-1.06 1.06l1.7 1.7a.75.75 0 0 0 1.06 0l3.68-3.7Z" />
          </svg>
          <p className="text-xs text-success-700">
            Score computed from timestamped activity data. Not self-reported.
          </p>
        </div>

        {/* Updated date */}
        <p className="text-center text-xs text-neutral-400 font-mono tabular-nums">
          Last updated: {new Date(data.computedAt).toLocaleDateString('en-US', {
            month: 'long', day: 'numeric', year: 'numeric',
          })}
        </p>
      </main>

      {/* Footer */}
      <footer className="border-t border-neutral-100 bg-surface-1 px-6 py-6 text-center">
        <p className="text-xs text-neutral-400">
          Powered by REGAIN — Evidence-backed career readiness
        </p>
        <a
          href="https://regain.altivum.ai"
          className="mt-2 inline-block text-xs font-medium text-primary-500 hover:text-primary-600 transition-colors"
        >
          Learn more
        </a>
      </footer>
    </div>
  );
}
