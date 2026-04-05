import type { GateCriterion } from '../../types';

const PHASES = ['Foundation', 'Expansion', 'Launch', 'Complete'] as const;

const PHASE_INDEX: Record<string, number> = {
  foundation: 0,
  momentum: 1,
  expansion: 1,
  acceleration: 1,
  launch: 2,
  transition: 2,
  complete: 3,
};

interface PhaseTrackProps {
  currentPhase: string;
  gatesMet: Record<string, GateCriterion>;
  startDate: string;
}

export default function PhaseTrack({ currentPhase, gatesMet, startDate }: PhaseTrackProps) {
  const idx = PHASE_INDEX[currentPhase.toLowerCase()] ?? 0;

  return (
    <div className="animate-fade-in-up" style={{ animationDelay: '100ms', animationFillMode: 'backwards' }}>
      <div className="flex items-center justify-between">
        {PHASES.map((phase, i) => (
          <div key={phase} className="flex items-center">
            {/* Node */}
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={`h-3 w-3 rounded-full transition-all duration-300 ${
                  i < idx
                    ? 'bg-primary-500'
                    : i === idx
                      ? 'bg-primary-500 ring-4 ring-primary-100 animate-glow-pulse'
                      : 'bg-neutral-200'
                }`}
              />
              <span
                className={`text-xs transition-colors ${
                  i < idx
                    ? 'font-medium text-neutral-700'
                    : i === idx
                      ? 'font-semibold text-primary-600'
                      : 'text-neutral-300'
                }`}
              >
                {phase}
              </span>
            </div>
            {/* Connector line */}
            {i < PHASES.length - 1 && (
              <div
                className={`mx-2 h-px w-8 sm:w-16 md:w-24 transition-colors ${
                  i < idx ? 'bg-primary-300' : 'bg-neutral-200'
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Gate criteria summary */}
      <div className="mt-3 flex flex-wrap gap-3">
        {Object.entries(gatesMet).map(([gate, criterion]) => (
          <span
            key={gate}
            className={`inline-flex items-center gap-1 text-xs ${
              criterion.met ? 'text-success-500' : 'text-neutral-400'
            }`}
          >
            <svg className="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
              {criterion.met ? (
                <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1Zm3.22 4.72a.75.75 0 0 0-1.06-1.06L7 7.82 5.84 6.66a.75.75 0 0 0-1.06 1.06l1.7 1.7a.75.75 0 0 0 1.06 0l3.68-3.7Z" />
              ) : (
                <circle cx="8" cy="8" r="6" strokeWidth="1.5" stroke="currentColor" fill="none" />
              )}
            </svg>
            {criterion.current}/{criterion.required} missions
          </span>
        ))}
        {startDate && (
          <span className="text-xs text-neutral-400">
            Started {new Date(startDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
          </span>
        )}
      </div>
    </div>
  );
}
