import type { ToolStep } from '../../hooks/useStreamingCoaching';
import SectionLabel from './SectionLabel';

interface AgentActivityFeedProps {
  steps: ToolStep[];
  visible: boolean;
}

export default function AgentActivityFeed({ steps, visible }: AgentActivityFeedProps) {
  if (steps.length === 0) return null;

  return (
    <div
      className={`flex justify-start transition-all duration-500 ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2 pointer-events-none'
      }`}
    >
      <div className="bg-surface-2 border border-neutral-200/60 rounded-[var(--radius-card)] rounded-bl-sm px-4 py-3 max-w-[75%]">
        <SectionLabel>Working on it</SectionLabel>
        <div className="mt-2 space-y-1.5">
          {steps.map((step, i) => (
            <div
              key={`${step.tool}-${i}`}
              className="flex items-center gap-2 animate-fade-in-up"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              {step.status === 'active' ? (
                <div className="h-3.5 w-3.5 rounded-full border-2 border-primary-200 border-t-primary-500 animate-spin shrink-0" />
              ) : (
                <svg
                  className="h-3.5 w-3.5 text-primary-500 animate-scale-in shrink-0"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
              )}
              <span
                className={`text-xs ${step.status === 'active' ? 'text-neutral-600' : 'text-neutral-400'}`}
              >
                {step.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
