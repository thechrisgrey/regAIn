import type { HotSkillGap } from '../../types';
import { Link } from 'react-router-dom';

interface RadarDataPoint {
  label: string;
  target: number;
  user: number;
}

interface MarketAlignmentRadarProps {
  targetSkills: Record<string, number>;
  userSkills: Record<string, number>;
  hotSkillsGap: HotSkillGap[];
  matchedSkills: number;
  totalTargetSkills: number;
  targetRole: string;
}

function RadarChart({ data }: { data: RadarDataPoint[] }) {
  const size = 280;
  const cx = size / 2;
  const cy = size / 2;
  const levels = 4;
  const maxR = 110;

  if (data.length < 3) return null;

  function getPoint(index: number, value: number) {
    const angle = (Math.PI * 2 * index) / data.length - Math.PI / 2;
    const r = (value * maxR);
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  }

  function polygon(getValue: (d: RadarDataPoint) => number) {
    return data
      .map((d, i) => {
        const p = getPoint(i, getValue(d));
        return `${p.x},${p.y}`;
      })
      .join(' ');
  }

  // Normalize values to 0-1
  const maxVal = Math.max(...data.map(d => Math.max(d.target, d.user)), 0.01);

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[280px] mx-auto">
      {/* Grid rings */}
      {Array.from({ length: levels }, (_, i) => {
        const r = ((i + 1) / levels) * maxR;
        const points = data.map((_, j) => {
          const angle = (Math.PI * 2 * j) / data.length - Math.PI / 2;
          return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
        }).join(' ');
        return (
          <polygon
            key={i}
            points={points}
            fill="none"
            stroke="var(--color-neutral-100)"
            strokeWidth="0.5"
          />
        );
      })}

      {/* Axis lines */}
      {data.map((_, i) => {
        const p = getPoint(i, 1);
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={p.x}
            y2={p.y}
            stroke="var(--color-neutral-100)"
            strokeWidth="0.5"
          />
        );
      })}

      {/* Target boundary (outer shape) */}
      <polygon
        points={polygon(d => d.target / maxVal)}
        fill="var(--color-neutral-100)"
        fillOpacity="0.5"
        stroke="var(--color-neutral-300)"
        strokeWidth="1"
      />

      {/* User fill (inner shape) */}
      <polygon
        points={polygon(d => d.user / maxVal)}
        fill="var(--color-primary-400)"
        fillOpacity="0.25"
        stroke="var(--color-primary-500)"
        strokeWidth="1.5"
      />

      {/* Data point dots */}
      {data.map((d, i) => {
        const p = getPoint(i, d.user / maxVal);
        return (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r="3"
            fill="var(--color-primary-500)"
          />
        );
      })}

      {/* Labels */}
      {data.map((d, i) => {
        const labelR = maxR + 20;
        const angle = (Math.PI * 2 * i) / data.length - Math.PI / 2;
        const x = cx + labelR * Math.cos(angle);
        const y = cy + labelR * Math.sin(angle);
        const anchor = Math.abs(angle + Math.PI / 2) < 0.1
          ? 'middle'
          : angle > -Math.PI / 2 && angle < Math.PI / 2
            ? 'start'
            : 'end';
        return (
          <text
            key={i}
            x={x}
            y={y}
            textAnchor={anchor}
            dominantBaseline="central"
            className="fill-neutral-500"
            style={{ fontSize: '9px', fontFamily: 'var(--font-sans)' }}
          >
            {d.label.length > 14 ? d.label.slice(0, 12) + '..' : d.label}
          </text>
        );
      })}
    </svg>
  );
}

export default function MarketAlignmentRadar({
  targetSkills,
  userSkills,
  hotSkillsGap,
  matchedSkills,
  totalTargetSkills,
  targetRole,
}: MarketAlignmentRadarProps) {
  const data: RadarDataPoint[] = Object.entries(targetSkills)
    .slice(0, 10)
    .map(([skill, target]) => ({
      label: skill,
      target,
      user: userSkills[skill.toLowerCase()] ?? 0,
    }));

  return (
    <div className="animate-fade-in-up" style={{ animationDelay: '400ms', animationFillMode: 'backwards' }}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-widest text-neutral-400">
          Market Alignment
        </span>
        <span className="text-xs font-mono tabular-nums text-neutral-500">
          {matchedSkills}/{totalTargetSkills} skills matched
        </span>
      </div>

      {data.length >= 3 ? (
        <div className="mt-4">
          <RadarChart data={data} />
        </div>
      ) : (
        <p className="mt-4 text-sm text-neutral-400">
          Insufficient market data for {targetRole || 'your target role'}.
          Complete more missions to build your skill profile.
        </p>
      )}

      {/* Hot Skills Gap */}
      {hotSkillsGap.length > 0 && (
        <div className="mt-5">
          <span className="text-[11px] font-medium uppercase tracking-widest text-neutral-400">
            Top Skill Gaps
          </span>
          <div className="mt-2 space-y-2">
            {hotSkillsGap.map(gap => (
              <div
                key={gap.skill}
                className="flex items-center justify-between rounded-[var(--radius-button)] bg-surface-2 px-3 py-2"
              >
                <span className="text-sm font-medium text-neutral-700 capitalize">
                  {gap.skill}
                </span>
                <Link
                  to="/missions"
                  className="text-xs font-medium text-primary-500 hover:text-primary-600 transition-colors"
                >
                  Build this skill
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
