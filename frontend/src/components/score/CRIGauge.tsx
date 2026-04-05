import { useEffect, useRef, useState } from 'react';

interface CRIGaugeProps {
  score: number;
  evidenceCount: number;
  onClick?: () => void;
}

/**
 * SVG arc gauge for the Composite Readiness Index.
 *
 * Draws a 240-degree arc that fills from 0 to the score on mount.
 * The score number is centered, rendered in the stat-value gradient.
 * Evidence count displayed below in JetBrains Mono.
 */
export default function CRIGauge({ score, evidenceCount, onClick }: CRIGaugeProps) {
  const [animated, setAnimated] = useState(0);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    const start = performance.now();
    const duration = 1200;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(1, elapsed / duration);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setAnimated(eased * score);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      }
    }
    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [score]);

  // Arc geometry: 240 degrees, starting at 150 degrees (bottom-left)
  const cx = 120;
  const cy = 120;
  const r = 100;
  const startAngle = 150;
  const totalArc = 240;

  function polarToCartesian(angle: number) {
    const rad = ((angle - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function describeArc(endAngle: number) {
    const start = polarToCartesian(startAngle);
    const end = polarToCartesian(startAngle + endAngle);
    const largeArc = endAngle > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
  }

  const fillAngle = (animated / 100) * totalArc;

  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative mx-auto block w-[240px] cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-2 rounded-full"
      aria-label={`Career Readiness Index: ${Math.round(animated)} out of 100. Click for breakdown.`}
    >
      <svg viewBox="0 0 240 240" className="w-full h-full" role="img">
        <defs>
          <linearGradient id="cri-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--color-primary-400)" />
            <stop offset="60%" stopColor="var(--color-primary-500)" />
            <stop offset="100%" stopColor="var(--color-accent-400)" />
          </linearGradient>
          <filter id="cri-glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background track */}
        <path
          d={describeArc(totalArc)}
          fill="none"
          stroke="var(--color-surface-3)"
          strokeWidth="12"
          strokeLinecap="round"
        />

        {/* Filled arc */}
        {fillAngle > 0.5 && (
          <path
            d={describeArc(fillAngle)}
            fill="none"
            stroke="url(#cri-gradient)"
            strokeWidth="12"
            strokeLinecap="round"
            filter="url(#cri-glow)"
            className="transition-all duration-75"
          />
        )}

        {/* Score number */}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          dominantBaseline="central"
          className="fill-neutral-900"
          style={{ fontSize: '56px', fontFamily: 'var(--font-sans)', fontWeight: 600 }}
        >
          {Math.round(animated)}
        </text>

        {/* Label */}
        <text
          x={cx}
          y={cy + 32}
          textAnchor="middle"
          dominantBaseline="central"
          className="fill-neutral-400"
          style={{ fontSize: '11px', fontFamily: 'var(--font-sans)', fontWeight: 500, letterSpacing: '0.05em', textTransform: 'uppercase' as const }}
        >
          Career Readiness
        </text>
      </svg>

      {/* Evidence count below */}
      <p className="mt-1 text-center text-xs font-mono tabular-nums text-neutral-400 tracking-wide group-hover:text-neutral-500 transition-colors">
        Backed by {evidenceCount} {evidenceCount === 1 ? 'piece' : 'pieces'} of documented evidence
      </p>
    </button>
  );
}
