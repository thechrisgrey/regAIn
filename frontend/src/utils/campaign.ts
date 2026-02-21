import type { Campaign } from '../types';

export const DISPLAY_PHASES = ['Foundation', 'Expansion', 'Launch'] as const;

export function phaseIndex(phase: Campaign['phase']): number {
  switch (phase) {
    case 'foundation':
      return 0;
    case 'momentum':
    case 'acceleration':
      return 1;
    case 'transition':
      return 2;
  }
}

export function phaseLabel(phase: Campaign['phase']): string {
  return DISPLAY_PHASES[phaseIndex(phase)];
}

export function phaseProgress(phase: Campaign['phase']): number {
  switch (phase) {
    case 'foundation':
      return 33;
    case 'momentum':
      return 50;
    case 'acceleration':
      return 66;
    case 'transition':
      return 100;
  }
}

export function daysActive(startDate: string): number {
  const start = new Date(startDate);
  const now = new Date();
  return Math.max(1, Math.floor((now.getTime() - start.getTime()) / 86400000));
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}
