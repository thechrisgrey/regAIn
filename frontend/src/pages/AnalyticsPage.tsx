import { useEffect, useMemo } from 'react';
import { useAnalytics } from '../hooks/useAnalytics';
import { useMutationBus } from '../hooks/useMutationBus';
import type {
  SkillBreakdownItem,
  ActivityHeatmapDay,
  VelocityWeek,
  CampaignEta,
  MarketAlignment,
} from '../types';
import { Card, SectionLabel, ProgressBar, Badge, Button, SkeletonBlock } from '../components/ui';

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function Skeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-6">
          <SkeletonBlock className="h-2.5 w-32" />
          <SkeletonBlock className="mt-5 h-8 w-16" />
          <SkeletonBlock className="mt-3 h-1.5 w-full" />
          <div className="mt-5 flex gap-8">
            <div>
              <SkeletonBlock className="h-6 w-10" />
              <SkeletonBlock className="mt-1 h-2 w-16" />
            </div>
            <div>
              <SkeletonBlock className="h-6 w-14" />
              <SkeletonBlock className="mt-1 h-2 w-20" />
            </div>
          </div>
        </Card>
        <Card className="p-6">
          <SkeletonBlock className="h-2.5 w-28" />
          <SkeletonBlock className="mt-5 h-32 w-full" />
        </Card>
      </div>
      <Card className="p-6">
        <SkeletonBlock className="h-2.5 w-32" />
        <SkeletonBlock className="mt-5 h-24 w-full" />
      </Card>
      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-6">
          <SkeletonBlock className="h-2.5 w-28" />
          <div className="mt-5 space-y-3">
            {[1, 2, 3, 4].map(i => (
              <SkeletonBlock key={i} className="h-4 w-full" />
            ))}
          </div>
        </Card>
        <Card className="p-6">
          <SkeletonBlock className="h-2.5 w-20" />
          <div className="mt-5 flex flex-wrap gap-2">
            {[1, 2, 3].map(i => (
              <SkeletonBlock key={i} className="h-7 w-28" />
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

function AnalyticsError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <p className="text-sm font-medium text-neutral-900">
        Unable to load analytics
      </p>
      <p className="mt-1.5 text-sm text-neutral-500">{message}</p>
      <Button onClick={onRetry} className="mt-6">
        Retry
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Campaign ETA
// ---------------------------------------------------------------------------

const confidenceBadgeVariant: Record<string, 'success' | 'info' | 'warning'> = {
  high: 'success',
  medium: 'info',
  low: 'warning',
};

function CampaignEtaCard({ eta }: { eta: CampaignEta | null }) {
  if (!eta) {
    return (
      <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '0ms' }}>
        <SectionLabel>Campaign Estimate</SectionLabel>
        <p className="mt-5 text-sm leading-relaxed text-neutral-500">
          No active campaign. Complete onboarding to see projected completion.
        </p>
      </Card>
    );
  }

  const pct = Math.round(eta.completionRate * 100);

  return (
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '0ms' }}>
      <SectionLabel>Campaign Estimate</SectionLabel>

      <div className="mt-5 flex items-baseline gap-2">
        <span className="stat-value text-3xl font-medium font-mono tabular-nums">
          {eta.estimatedDaysRemaining === 0
            ? 'Complete'
            : `${eta.estimatedDaysRemaining}d`}
        </span>
        <Badge variant={confidenceBadgeVariant[eta.confidence] ?? 'info'}>
          {eta.confidence}
        </Badge>
      </div>

      <ProgressBar value={pct} className="mt-3" />

      <div className="mt-5 flex gap-8">
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-xl font-medium font-mono tabular-nums">
            {pct}%
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">completion</p>
        </div>
        <div className="rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
          <p className="stat-value text-xl font-medium font-mono tabular-nums">
            {eta.dailyRate.toFixed(1)}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500">missions / day</p>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Velocity Chart (SVG bar chart)
// ---------------------------------------------------------------------------

function VelocityChart({ weeks }: { weeks: VelocityWeek[] }) {
  const maxCompleted = Math.max(1, ...weeks.map(w => w.completed));

  const barWidth = 28;
  const barGap = 8;
  const chartHeight = 120;
  const labelHeight = 24;
  const svgWidth = weeks.length * (barWidth + barGap) - barGap;
  const svgHeight = chartHeight + labelHeight;

  return (
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '60ms' }}>
      <SectionLabel>Weekly Velocity</SectionLabel>

      <div className="mt-5 overflow-x-auto">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full"
          style={{ minWidth: 320 }}
          aria-label="Weekly mission completion chart"
          role="img"
        >
          {weeks.map((week, i) => {
            const barHeight = (week.completed / maxCompleted) * chartHeight;
            const x = i * (barWidth + barGap);
            const y = chartHeight - barHeight;

            // Label: short month/day from weekStart
            const d = new Date(week.weekStart + 'T00:00:00');
            const label = d.toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
            });

            return (
              <g key={week.weekStart}>
                {/* Bar */}
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={Math.max(barHeight, 2)}
                  rx={3}
                  fill="var(--color-primary-400)"
                  opacity={week.completed > 0 ? 1 : 0.25}
                />
                {/* Count label on top of bar */}
                {week.completed > 0 && (
                  <text
                    x={x + barWidth / 2}
                    y={y - 4}
                    textAnchor="middle"
                    className="fill-neutral-500"
                    fontSize={9}
                    fontFamily="var(--font-mono)"
                  >
                    {week.completed}
                  </text>
                )}
                {/* Week label */}
                <text
                  x={x + barWidth / 2}
                  y={chartHeight + 14}
                  textAnchor="middle"
                  className="fill-neutral-400"
                  fontSize={8}
                  fontFamily="var(--font-sans)"
                >
                  {label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Activity Heatmap (90-day grid)
// ---------------------------------------------------------------------------

function heatmapColor(count: number): string {
  if (count === 0) return 'var(--color-surface-3)';
  if (count === 1) return 'var(--color-peach-100)';
  if (count <= 3) return 'var(--color-peach-200)';
  return 'var(--color-primary-300)';
}

function ActivityHeatmap({ days }: { days: ActivityHeatmapDay[] }) {
  // Build the grid: 7 rows (Mon-Sun) x 13 columns (weeks).
  // days array is sorted chronologically (90 entries).
  const grid = useMemo(() => {
    const cells: { date: string; count: number; col: number; row: number }[] = [];

    if (days.length === 0) return { cells, months: [] as { label: string; col: number }[] };

    // First date determines offset into the week.
    const firstDate = new Date(days[0].date + 'T00:00:00');
    const startDow = firstDate.getDay(); // 0=Sun

    for (let i = 0; i < days.length; i++) {
      const dow = (startDow + i) % 7;
      const weekIdx = Math.floor((startDow + i) / 7);
      cells.push({
        date: days[i].date,
        count: days[i].count,
        col: weekIdx,
        row: dow,
      });
    }

    // Month labels: find the first occurrence of each month.
    const seenMonths = new Set<string>();
    const months: { label: string; col: number }[] = [];
    for (const cell of cells) {
      const d = new Date(cell.date + 'T00:00:00');
      const key = `${d.getFullYear()}-${d.getMonth()}`;
      if (!seenMonths.has(key)) {
        seenMonths.add(key);
        months.push({
          label: d.toLocaleDateString('en-US', { month: 'short' }),
          col: cell.col,
        });
      }
    }

    return { cells, months };
  }, [days]);

  const cellSize = 13;
  const cellGap = 3;
  const labelOffsetX = 20;
  const labelOffsetY = 16;
  const totalCols = Math.max(1, ...grid.cells.map(c => c.col)) + 1;

  const svgWidth = labelOffsetX + totalCols * (cellSize + cellGap);
  const svgHeight = labelOffsetY + 7 * (cellSize + cellGap);

  const dayLabels = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  return (
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '120ms' }}>
      <SectionLabel>Activity (90 days)</SectionLabel>

      <div className="mt-5 overflow-x-auto">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full"
          style={{ minWidth: 280 }}
          aria-label="90-day activity heatmap"
          role="img"
        >
          {/* Month labels */}
          {grid.months.map(m => (
            <text
              key={`month-${m.col}`}
              x={labelOffsetX + m.col * (cellSize + cellGap)}
              y={10}
              className="fill-neutral-400"
              fontSize={9}
              fontFamily="var(--font-sans)"
            >
              {m.label}
            </text>
          ))}

          {/* Day-of-week labels */}
          {[1, 3, 5].map(row => (
            <text
              key={`dow-${row}`}
              x={0}
              y={labelOffsetY + row * (cellSize + cellGap) + cellSize - 3}
              className="fill-neutral-400"
              fontSize={8}
              fontFamily="var(--font-sans)"
            >
              {dayLabels[row]}
            </text>
          ))}

          {/* Cells */}
          {grid.cells.map(cell => (
            <rect
              key={cell.date}
              x={labelOffsetX + cell.col * (cellSize + cellGap)}
              y={labelOffsetY + cell.row * (cellSize + cellGap)}
              width={cellSize}
              height={cellSize}
              rx={2}
              fill={heatmapColor(cell.count)}
            >
              <title>
                {cell.date}: {cell.count} {cell.count === 1 ? 'activity' : 'activities'}
              </title>
            </rect>
          ))}
        </svg>
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center gap-1.5 text-xs text-neutral-400">
        <span>Less</span>
        {[0, 1, 2, 4].map(n => (
          <span
            key={n}
            className="inline-block h-3 w-3 rounded-sm"
            style={{ backgroundColor: heatmapColor(n) }}
          />
        ))}
        <span>More</span>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Skill Bar Chart
// ---------------------------------------------------------------------------

function SkillBarChart({ skills }: { skills: SkillBreakdownItem[] }) {
  const visible = skills.slice(0, 10);

  return (
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '240ms' }}>
      <SectionLabel>Skill Breakdown</SectionLabel>

      {visible.length === 0 ? (
        <p className="mt-5 text-sm leading-relaxed text-neutral-500">
          Complete missions and log evidence to see your skill distribution.
        </p>
      ) : (
        <div className="mt-5 space-y-3">
          {visible.map((item, i) => (
            <div
              key={item.skill}
              className="animate-fade-in-up"
              style={{ animationDelay: `${200 + i * 40}ms` }}
            >
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-neutral-700 truncate max-w-[180px]">
                  {item.skill}
                </span>
                <span className="font-mono tabular-nums text-neutral-400 ml-2 shrink-0">
                  {item.count}
                </span>
              </div>
              <div className="mt-1 h-2 w-full overflow-hidden rounded-[var(--radius-badge)] bg-neutral-100">
                <div
                  className="h-full rounded-[var(--radius-badge)] bg-primary-400 transition-all duration-700 ease-out"
                  style={{ width: `${Math.round(item.ratio * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Market Alignment
// ---------------------------------------------------------------------------

function MarketAlignmentCard({
  alignment,
}: {
  alignment: MarketAlignment | null;
}) {
  if (!alignment) {
    return (
      <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '180ms' }}>
        <SectionLabel>Market Alignment</SectionLabel>
        <p className="mt-5 text-sm leading-relaxed text-neutral-500">
          Set a target role in your{' '}
          <a href="/profile" className="text-primary-600 underline underline-offset-2">
            profile
          </a>{' '}
          to see market alignment.
        </p>
      </Card>
    );
  }

  const pct = Math.round(alignment.alignmentPct);

  return (
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '180ms' }}>
      <div className="flex items-start justify-between">
        <div>
          <SectionLabel>Market Alignment</SectionLabel>
          <p className="mt-0.5 text-xs text-neutral-400">{alignment.targetRole}</p>
        </div>
      </div>

      <div className="mt-5 rounded-[var(--radius-button)] bg-surface-2 px-4 py-3">
        <p className="stat-value text-3xl font-medium font-mono tabular-nums">
          {pct}%
        </p>
      </div>
      <ProgressBar value={pct} className="mt-2" />

      {alignment.topGaps.length > 0 && (
        <div className="mt-5">
          <p className="text-[11px] font-medium uppercase tracking-widest text-neutral-500">
            Top Gaps
          </p>
          <div className="mt-2 space-y-2">
            {alignment.topGaps.map((gap) => (
              <div key={gap.skill}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-neutral-700 truncate max-w-[180px]">
                    {gap.skill}
                  </span>
                  <span className="font-mono tabular-nums text-neutral-400 ml-2 shrink-0">
                    {gap.demand}% of postings
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-[var(--radius-badge)] bg-neutral-100">
                  <div
                    className="h-full rounded-[var(--radius-badge)] bg-accent-400 transition-all duration-700 ease-out"
                    style={{ width: `${gap.demand}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {alignment.topStrengths.length > 0 && (
        <div className="mt-5">
          <p className="text-[11px] font-medium uppercase tracking-widest text-neutral-500">
            Strengths
          </p>
          <div className="mt-2 space-y-2">
            {alignment.topStrengths.map((s) => (
              <div key={s.skill}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-neutral-700 truncate max-w-[180px]">
                    {s.skill}
                  </span>
                  <span className="font-mono tabular-nums text-neutral-400 ml-2 shrink-0">
                    {Math.round(s.userScore * 100)}%
                  </span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-[var(--radius-badge)] bg-neutral-100">
                  <div
                    className="h-full rounded-[var(--radius-badge)] bg-success-400 transition-all duration-700 ease-out"
                    style={{ width: `${Math.round(s.userScore * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="mt-4 text-[10px] text-neutral-400">
        Calculated {new Date(alignment.calculatedAt).toLocaleDateString()}
      </p>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Skill Gaps List
// ---------------------------------------------------------------------------

function SkillGapsList({ gaps }: { gaps: string[] }) {
  return (
    <Card className="p-6 animate-fade-in-up" style={{ animationDelay: '300ms' }}>
      <SectionLabel>Skill Gaps</SectionLabel>

      {gaps.length === 0 ? (
        <p className="mt-5 text-sm leading-relaxed text-neutral-500">
          All campaign skills have evidence. Keep building depth.
        </p>
      ) : (
        <div className="mt-5 flex flex-wrap gap-2">
          {gaps.map(skill => (
            <span
              key={skill}
              className="inline-flex items-center gap-2 rounded-[var(--radius-badge)] bg-neutral-50 px-3 py-1.5 text-xs font-medium text-neutral-600 ring-1 ring-neutral-200/60"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-accent-400" />
              {skill}
            </span>
          ))}
        </div>
      )}

      {gaps.length > 0 && (
        <p className="mt-4 text-xs text-neutral-400">
          {gaps.length} campaign {gaps.length === 1 ? 'skill' : 'skills'} without
          evidence yet
        </p>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function AnalyticsPage() {
  const { data, loading, error, fetchAnalytics } = useAnalytics();
  const { setPageSnapshot } = useMutationBus();

  useEffect(() => {
    void fetchAnalytics();
  }, [fetchAnalytics]);

  useEffect(() => {
    if (!data) return;
    const topSkills = data.skillBreakdown.slice(0, 5).map(s => ({
      skill: s.skill,
      count: s.count,
    }));
    const activeDaysThisWeek = data.activityHeatmap
      .slice(-7)
      .filter(d => d.count > 0).length;
    const totalCompleted = data.velocityTrend.weeks.reduce(
      (sum, w) => sum + w.completed,
      0,
    );
    setPageSnapshot({
      page: 'analytics',
      totalCompletedInTrend: totalCompleted,
      weekCount: data.velocityTrend.weeks.length,
      campaignEta: data.campaignEta
        ? {
            daysRemaining: data.campaignEta.estimatedDaysRemaining,
            completionRate: data.campaignEta.completionRate,
            confidence: data.campaignEta.confidence,
          }
        : null,
      topSkills,
      skillGaps: data.skillSuggestions,
      activeDaysThisWeek,
    });
  }, [data, setPageSnapshot]);

  if (loading || (!data && !error)) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
            Analytics
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            Career intelligence and progress tracking
          </p>
        </div>
        <Skeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
            Analytics
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            Career intelligence and progress tracking
          </p>
        </div>
        <AnalyticsError message={error} onRetry={() => void fetchAnalytics()} />
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
          Analytics
        </h1>
        <p className="mt-1 text-sm text-neutral-500">
          Career intelligence and progress tracking
        </p>
      </div>

      {/* Row 1: Campaign ETA + Velocity */}
      <div className="grid gap-6 md:grid-cols-2">
        <CampaignEtaCard eta={data.campaignEta} />
        <VelocityChart weeks={data.velocityTrend.weeks} />
      </div>

      {/* Row 2: Activity Heatmap (full width) */}
      <ActivityHeatmap days={data.activityHeatmap} />

      {/* Row 3: Market Alignment + Skill Breakdown */}
      <div className="grid gap-6 md:grid-cols-2">
        <MarketAlignmentCard alignment={data.marketAlignment} />
        <SkillBarChart skills={data.skillBreakdown} />
      </div>

      {/* Row 4: Skill Gaps (full width) */}
      <SkillGapsList gaps={data.skillSuggestions} />
    </div>
  );
}
