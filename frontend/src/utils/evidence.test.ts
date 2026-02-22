import { describe, it, expect } from 'vitest';
import { computeSkillStats } from './evidence';
import type { Evidence } from '../types';

function makeEvidence(skillTag: string, id = 'e-1'): Evidence {
  return {
    userId: 'user-1',
    evidenceId: id,
    missionId: 'm-1',
    skillTag,
    reflection: 'test',
    createdAt: '2025-01-01T00:00:00Z',
  };
}

describe('computeSkillStats', () => {
  it('returns empty array for empty input', () => {
    expect(computeSkillStats([])).toEqual([]);
  });

  it('counts correctly for a single skill', () => {
    const evidence = [
      makeEvidence('Python', 'e-1'),
      makeEvidence('Python', 'e-2'),
      makeEvidence('Python', 'e-3'),
    ];
    const result = computeSkillStats(evidence);

    expect(result).toHaveLength(1);
    expect(result[0].skill).toBe('Python');
    expect(result[0].count).toBe(3);
    expect(result[0].ratio).toBe(1);
  });

  it('sorts by frequency descending', () => {
    const evidence = [
      makeEvidence('AWS', 'e-1'),
      makeEvidence('Python', 'e-2'),
      makeEvidence('Python', 'e-3'),
      makeEvidence('Python', 'e-4'),
      makeEvidence('AWS', 'e-5'),
      makeEvidence('Docker', 'e-6'),
    ];
    const result = computeSkillStats(evidence);

    expect(result[0].skill).toBe('Python');
    expect(result[0].count).toBe(3);
    expect(result[1].skill).toBe('AWS');
    expect(result[1].count).toBe(2);
    expect(result[2].skill).toBe('Docker');
    expect(result[2].count).toBe(1);
  });

  it('normalizes ratio to max count', () => {
    const evidence = [
      makeEvidence('Python', 'e-1'),
      makeEvidence('Python', 'e-2'),
      makeEvidence('Python', 'e-3'),
      makeEvidence('Python', 'e-4'),
      makeEvidence('AWS', 'e-5'),
      makeEvidence('AWS', 'e-6'),
      makeEvidence('Docker', 'e-7'),
    ];
    const result = computeSkillStats(evidence);

    expect(result[0].ratio).toBe(1);       // 4/4
    expect(result[1].ratio).toBe(0.5);     // 2/4
    expect(result[2].ratio).toBe(0.25);    // 1/4
  });

  it('handles single evidence item', () => {
    const result = computeSkillStats([makeEvidence('SQL')]);

    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({ skill: 'SQL', count: 1, ratio: 1 });
  });

  it('treats different skill tags as separate entries', () => {
    const evidence = [
      makeEvidence('Python', 'e-1'),
      makeEvidence('python', 'e-2'),  // different case = different tag
    ];
    const result = computeSkillStats(evidence);

    expect(result).toHaveLength(2);
    expect(result[0].count).toBe(1);
    expect(result[1].count).toBe(1);
  });
});
