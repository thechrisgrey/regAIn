interface SparklinePoint {
  value: number;
}

interface DimensionTileProps {
  name: string;
  score: number;
  trend: 'up' | 'down' | 'flat';
  sparkline?: SparklinePoint[];
  onClick?: () => void;
  delay?: number;
}

function Sparkline({ points }: { points: SparklinePoint[] }) {
  if (points.length < 2) return null;
  const w = 64;
  const h = 24;
  const max = Math.max(...points.map(p => p.value), 1);
  const min = Math.min(...points.map(p => p.value), 0);
  const range = max - min || 1;

  const coords = points.map((p, i) => ({
    x: (i / (points.length - 1)) * w,
    y: h - ((p.value - min) / range) * h,
  }));

  const d = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`).join(' ');

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0">
      <path d={d} fill="none" stroke="var(--color-primary-300)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TrendArrow({ trend }: { trend: 'up' | 'down' | 'flat' }) {
  if (trend === 'flat') {
    return <span className="text-xs text-neutral-400">--</span>;
  }
  return (
    <span className={`text-xs font-medium ${trend === 'up' ? 'text-success-500' : 'text-warning-500'}`}>
      {trend === 'up' ? (
        <svg className="inline h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 3.5l4.5 5H3.5z" />
        </svg>
      ) : (
        <svg className="inline h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 12.5l-4.5-5h9z" />
        </svg>
      )}
    </span>
  );
}

export default function DimensionTile({ name, score, trend, sparkline, onClick, delay = 0 }: DimensionTileProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex flex-col rounded-[var(--radius-card)] bg-surface-1 border border-neutral-100 p-4 text-left transition-all duration-200 hover:shadow-card-hover hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 animate-fade-in-up"
      style={{ animationDelay: `${delay}ms`, animationFillMode: 'backwards' }}
    >
      <span className="text-[11px] font-medium uppercase tracking-widest text-neutral-400">
        {name}
      </span>
      <div className="mt-2 flex items-end justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold font-mono tabular-nums text-neutral-900">
            {Math.round(score)}
          </span>
          <TrendArrow trend={trend} />
        </div>
        {sparkline && sparkline.length > 1 && <Sparkline points={sparkline} />}
      </div>
    </button>
  );
}
