import type { OnetScoredGroup } from '../../types';
import { Card, SectionLabel, ProgressBar } from '../ui';

interface OnetScoredSectionProps {
  title: string;
  group: OnetScoredGroup | undefined;
}

export default function OnetScoredSection({ title, group }: OnetScoredSectionProps) {
  if (!group?.element?.length) return null;

  // Sort by score descending, take top items
  const sorted = [...group.element]
    .filter(item => item.score?.value != null)
    .sort((a, b) => (b.score?.value ?? 0) - (a.score?.value ?? 0));

  if (sorted.length === 0) return null;

  return (
    <Card className="p-6">
      <SectionLabel>{title}</SectionLabel>
      <div className="mt-4 space-y-3">
        {sorted.map(item => (
          <div key={item.id}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-neutral-700">{item.name}</span>
              <span className="text-xs font-mono tabular-nums text-neutral-400">
                {item.score?.value}/5
              </span>
            </div>
            <ProgressBar value={item.score?.value ?? 0} max={5} />
          </div>
        ))}
      </div>
    </Card>
  );
}
