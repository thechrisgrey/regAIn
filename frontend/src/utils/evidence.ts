import type { Evidence } from '../types';

export interface SkillStat {
  skill: string;
  count: number;
  ratio: number;
}

/**
 * Compute per-skill evidence counts sorted by frequency (descending).
 * Each entry's `ratio` is normalized to the maximum count.
 */
export function computeSkillStats(evidence: Evidence[]): SkillStat[] {
  const counts = new Map<string, number>();
  for (const e of evidence) {
    counts.set(e.skillTag, (counts.get(e.skillTag) ?? 0) + 1);
  }
  const sorted = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([skill, count]) => ({ skill, count, ratio: 0 }));

  const max = sorted.length > 0 ? sorted[0].count : 1;
  for (const stat of sorted) {
    stat.ratio = stat.count / max;
  }
  return sorted;
}
