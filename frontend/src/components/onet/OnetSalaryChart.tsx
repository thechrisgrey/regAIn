import type { OnetSalary } from '../../types';
import { Card, SectionLabel, ProgressBar } from '../ui';

interface OnetSalaryChartProps {
  salary: OnetSalary | undefined;
}

function formatSalary(value: number | undefined): string {
  if (value == null) return '--';
  return `$${value.toLocaleString()}`;
}

export default function OnetSalaryChart({ salary }: OnetSalaryChartProps) {
  if (!salary) return null;

  const maxVal = salary.annual_90th_percentile ?? salary.annual_median ?? 100000;

  const percentiles = [
    { label: '10th percentile', value: salary.annual_10th_percentile },
    { label: 'Median', value: salary.annual_median },
    { label: '90th percentile', value: salary.annual_90th_percentile },
  ].filter(p => p.value != null);

  if (percentiles.length === 0) return null;

  return (
    <Card className="p-6">
      <SectionLabel>Annual Salary</SectionLabel>
      <div className="mt-4 space-y-3">
        {percentiles.map(p => (
          <div key={p.label}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-neutral-700">{p.label}</span>
              <span className="stat-value text-sm font-mono tabular-nums">
                {formatSalary(p.value)}
              </span>
            </div>
            <ProgressBar value={p.value!} max={maxVal} />
          </div>
        ))}
      </div>
    </Card>
  );
}
