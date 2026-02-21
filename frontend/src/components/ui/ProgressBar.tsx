import { useEffect, useRef, useState } from 'react';

interface ProgressBarProps {
  value: number;
  max?: number;
  className?: string;
  barClassName?: string;
}

export default function ProgressBar({
  value,
  max = 100,
  className = '',
  barClassName = 'bg-primary-500',
}: ProgressBarProps) {
  const [mounted, setMounted] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const pct = Math.min(100, Math.max(0, (value / max) * 100));

  useEffect(() => {
    const frame = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div
      ref={ref}
      className={`h-1 w-full overflow-hidden rounded-[var(--radius-badge)] bg-neutral-100 ${className}`}
    >
      <div
        className={`h-full rounded-[var(--radius-badge)] transition-all duration-700 ease-out ${barClassName}`}
        style={{ width: mounted ? `${pct}%` : '0%' }}
      />
    </div>
  );
}
