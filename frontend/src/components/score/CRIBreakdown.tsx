import type { DimensionDetail } from '../../types';

interface CRIBreakdownProps {
  open: boolean;
  onClose: () => void;
  cri: number;
  dimensions: {
    missionVelocityScore: number;
    evidenceDensityScore: number;
    marketAlignmentScore: number;
    phaseProgressionScore: number;
    adaptiveDifficultyScore: number;
  };
  detail: DimensionDetail;
  evidenceCount: number;
  missionsCompleted: number;
}

const WEIGHTS = [
  { key: 'evidenceDensityScore', label: 'Evidence Density', weight: 0.30 },
  { key: 'marketAlignmentScore', label: 'Market Alignment', weight: 0.25 },
  { key: 'missionVelocityScore', label: 'Mission Velocity', weight: 0.20 },
  { key: 'phaseProgressionScore', label: 'Phase Progression', weight: 0.15 },
  { key: 'adaptiveDifficultyScore', label: 'Adaptive Difficulty', weight: 0.10 },
] as const;

export default function CRIBreakdown({
  open,
  onClose,
  cri,
  dimensions,
  detail,
  evidenceCount,
  missionsCompleted,
}: CRIBreakdownProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-neutral-900/40 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-md rounded-[var(--radius-card)] bg-surface-1 p-6 shadow-elevated animate-scale-in">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-neutral-900">Score Breakdown</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1 text-neutral-400 hover:text-neutral-600 transition-colors"
            aria-label="Close"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>

        {/* CRI total */}
        <div className="mt-4 rounded-[var(--radius-button)] bg-surface-2 p-4 text-center">
          <span className="text-3xl font-semibold font-mono tabular-nums text-neutral-900">
            {cri.toFixed(1)}
          </span>
          <span className="ml-1 text-sm text-neutral-400">/ 100</span>
        </div>

        {/* Dimension breakdown */}
        <div className="mt-5 space-y-3">
          {WEIGHTS.map(({ key, label, weight }) => {
            const score = dimensions[key as keyof typeof dimensions];
            const contribution = score * weight;
            return (
              <div key={key}>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-neutral-600">{label}</span>
                  <span className="font-mono tabular-nums text-neutral-900">
                    {score.toFixed(1)}
                    <span className="text-neutral-300 text-xs ml-1">
                      x{weight} = {contribution.toFixed(1)}
                    </span>
                  </span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-surface-3 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary-400 transition-all duration-500"
                    style={{ width: `${Math.min(100, score)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Evidence summary */}
        <div className="mt-5 flex gap-4 text-center">
          <div className="flex-1 rounded-[var(--radius-button)] bg-surface-2 px-3 py-2">
            <p className="text-lg font-mono tabular-nums font-medium text-neutral-900">{missionsCompleted}</p>
            <p className="text-[10px] text-neutral-400 uppercase tracking-wider">Missions</p>
          </div>
          <div className="flex-1 rounded-[var(--radius-button)] bg-surface-2 px-3 py-2">
            <p className="text-lg font-mono tabular-nums font-medium text-neutral-900">{evidenceCount}</p>
            <p className="text-[10px] text-neutral-400 uppercase tracking-wider">Evidence</p>
          </div>
          <div className="flex-1 rounded-[var(--radius-button)] bg-surface-2 px-3 py-2">
            <p className="text-lg font-mono tabular-nums font-medium text-neutral-900">
              {detail.evidenceDensity.uniqueSkills}
            </p>
            <p className="text-[10px] text-neutral-400 uppercase tracking-wider">Skills</p>
          </div>
        </div>

        {/* Footer */}
        <p className="mt-5 text-center text-[10px] text-neutral-400 tracking-wide">
          Every point is backed by timestamped evidence. Not self-reported.
        </p>
      </div>
    </div>
  );
}
