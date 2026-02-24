import type { OnetKnowledgeGroup } from '../../types';
import { Card, SectionLabel } from '../ui';

interface OnetScoredSectionProps {
  title: string;
  groups: OnetKnowledgeGroup[] | null | undefined;
}

export default function OnetScoredSection({ title, groups }: OnetScoredSectionProps) {
  if (!groups?.length) return null;

  return (
    <Card className="p-6">
      <SectionLabel>{title}</SectionLabel>
      <div className="mt-4 space-y-4">
        {groups.map(group => (
          <div key={group.id}>
            <p className="text-xs font-medium uppercase tracking-wider text-neutral-500 mb-2">
              {group.name}
            </p>
            <ul className="space-y-1">
              {group.element.map(el => (
                <li key={el.id} className="flex items-start gap-2 text-sm text-neutral-700">
                  <span className="text-primary-500 mt-0.5 shrink-0">•</span>
                  {el.name}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Card>
  );
}
