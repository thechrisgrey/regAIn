const CATEGORY_COLORS: Record<string, string> = {
  reflection: 'var(--color-accent-400)',
  skill_building: 'var(--color-primary-500)',
  portfolio: 'var(--color-steel-300)',
  networking: 'var(--color-peach-200)',
  market_research: 'var(--color-primary-300)',
};

const CATEGORY_LABELS: Record<string, string> = {
  reflection: 'Reflection',
  skill_building: 'Skill Building',
  portfolio: 'Portfolio',
  networking: 'Networking',
  market_research: 'Market Research',
};

interface DifficultyTrajectoryProps {
  historyByCategory: Record<string, { day: number; difficulty: number }[]>;
  difficultyCeilings: Record<string, number>;
}

export default function DifficultyTrajectory({
  historyByCategory,
  difficultyCeilings,
}: DifficultyTrajectoryProps) {
  const categories = Object.keys(historyByCategory).filter(
    c => historyByCategory[c].length > 0,
  );

  if (categories.length === 0) {
    return (
      <div className="animate-fade-in-up" style={{ animationDelay: '500ms', animationFillMode: 'backwards' }}>
        <span className="text-[11px] font-medium uppercase tracking-widest text-neutral-400">
          Difficulty Trajectory
        </span>
        <p className="mt-3 text-sm text-neutral-400">
          Complete missions across categories to see your difficulty progression.
        </p>
      </div>
    );
  }

  // Chart dimensions
  const w = 400;
  const h = 160;
  const padL = 28;
  const padR = 8;
  const padT = 8;
  const padB = 24;
  const chartW = w - padL - padR;
  const chartH = h - padT - padB;

  // X range: all days across all categories
  let maxDay = 1;
  for (const points of Object.values(historyByCategory)) {
    for (const p of points) {
      if (p.day > maxDay) maxDay = p.day;
    }
  }

  function toX(day: number) {
    return padL + (day / maxDay) * chartW;
  }
  function toY(diff: number) {
    return padT + chartH - ((diff - 1) / 4) * chartH;
  }

  return (
    <div className="animate-fade-in-up" style={{ animationDelay: '500ms', animationFillMode: 'backwards' }}>
      <span className="text-[11px] font-medium uppercase tracking-widest text-neutral-400">
        Difficulty Trajectory
      </span>

      <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 w-full" role="img" aria-label="Difficulty progression over time">
        {/* Y-axis labels (difficulty 1-5) */}
        {[1, 2, 3, 4, 5].map(d => (
          <g key={d}>
            <line
              x1={padL}
              y1={toY(d)}
              x2={w - padR}
              y2={toY(d)}
              stroke="var(--color-neutral-100)"
              strokeWidth="0.5"
            />
            <text
              x={padL - 6}
              y={toY(d)}
              textAnchor="end"
              dominantBaseline="central"
              className="fill-neutral-300"
              style={{ fontSize: '9px', fontFamily: 'var(--font-mono)' }}
            >
              {d}
            </text>
          </g>
        ))}

        {/* Category lines */}
        {categories.map(cat => {
          const points = historyByCategory[cat];
          if (points.length < 1) return null;
          const color = CATEGORY_COLORS[cat] || 'var(--color-neutral-400)';

          const d = points
            .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(p.day)} ${toY(p.difficulty)}`)
            .join(' ');

          return (
            <g key={cat}>
              <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              {/* End dot */}
              {points.length > 0 && (
                <circle
                  cx={toX(points[points.length - 1].day)}
                  cy={toY(points[points.length - 1].difficulty)}
                  r="3"
                  fill={color}
                />
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend + milestones */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {categories.map(cat => {
          const color = CATEGORY_COLORS[cat] || 'var(--color-neutral-400)';
          const ceiling = difficultyCeilings[cat];
          return (
            <div key={cat} className="flex items-center gap-1.5">
              <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              <span className="text-xs text-neutral-500">
                {CATEGORY_LABELS[cat] || cat}
                {ceiling ? (
                  <span className="font-mono text-neutral-400"> (peak {ceiling})</span>
                ) : null}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
