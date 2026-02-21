import type { CSSProperties } from 'react';

interface SkeletonBlockProps {
  className?: string;
  style?: CSSProperties;
}

export default function SkeletonBlock({ className = 'h-4 w-full', style }: SkeletonBlockProps) {
  return (
    <div
      className={`rounded-[var(--radius-button)] bg-neutral-100 animate-shimmer ${className}`}
      style={{
        backgroundImage:
          'linear-gradient(90deg, transparent 0%, var(--color-neutral-50) 50%, transparent 100%)',
        backgroundSize: '200% 100%',
        ...style,
      }}
    />
  );
}
