import { useEffect, useRef, useState, useCallback } from 'react';
import type { SkillDetail } from '../../types';

interface SkillConstellationProps {
  skills: SkillDetail[];
}

interface SimNode {
  id: string;
  count: number;
  lastDate: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  opacity: number;
}

/**
 * Force-directed skill node graph.
 *
 * Uses a lightweight custom force simulation (no D3 dependency).
 * Nodes are sized by evidence count, colored by recency.
 * Falls back to a horizontal bar chart on screens < 640px.
 */
export default function SkillConstellation({ skills }: SkillConstellationProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const frameRef = useRef<number>(0);
  const [isMobile, setIsMobile] = useState(false);
  const [revealed, setRevealed] = useState(0);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 639px)');
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Initialize nodes
  useEffect(() => {
    if (!skills.length || isMobile) return;

    const maxCount = Math.max(...skills.map(s => s.count), 1);
    const cx = 200;
    const cy = 150;

    nodesRef.current = skills.slice(0, 20).map((s, i) => {
      const angle = (Math.PI * 2 * i) / Math.min(skills.length, 20);
      const spread = 60 + Math.random() * 40;
      return {
        id: s.skill,
        count: s.count,
        lastDate: s.lastDate,
        x: cx + Math.cos(angle) * spread,
        y: cy + Math.sin(angle) * spread,
        vx: 0,
        vy: 0,
        radius: 6 + (s.count / maxCount) * 18,
        opacity: 0,
      };
    });

    // Staggered reveal
    let revealCount = 0;
    const revealInterval = setInterval(() => {
      revealCount++;
      setRevealed(revealCount);
      if (revealCount >= nodesRef.current.length) clearInterval(revealInterval);
    }, 80);

    return () => clearInterval(revealInterval);
  }, [skills, isMobile]);

  // Force simulation + render loop
  const simulate = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const nodes = nodesRef.current;
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;

    // Forces
    for (const node of nodes) {
      // Center gravity
      node.vx += (cx - node.x) * 0.002;
      node.vy += (cy - node.y) * 0.002;

      // Repulsion between nodes
      for (const other of nodes) {
        if (node === other) continue;
        const dx = node.x - other.x;
        const dy = node.y - other.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const minDist = node.radius + other.radius + 8;
        if (dist < minDist) {
          const force = (minDist - dist) / dist * 0.3;
          node.vx += dx * force;
          node.vy += dy * force;
        }
      }

      // Damping
      node.vx *= 0.85;
      node.vy *= 0.85;
      node.x += node.vx;
      node.y += node.vy;

      // Clamp to canvas
      node.x = Math.max(node.radius, Math.min(w - node.radius, node.x));
      node.y = Math.max(node.radius, Math.min(h - node.radius, node.y));

      // Fade in
      if (node.opacity < 1) {
        node.opacity = Math.min(1, node.opacity + 0.08);
      }
    }

    // Render
    ctx.clearRect(0, 0, w, h);

    // Edges: connect nodes that are close
    ctx.strokeStyle = 'rgba(145, 109, 101, 0.08)';
    ctx.lineWidth = 1;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 100) {
          const alpha = Math.min(nodes[i].opacity, nodes[j].opacity) * (1 - dist / 100) * 0.3;
          ctx.globalAlpha = alpha;
          ctx.beginPath();
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(nodes[j].x, nodes[j].y);
          ctx.stroke();
        }
      }
    }

    // Nodes
    for (const node of nodes) {
      if (node.opacity <= 0) continue;

      // Recency color: warm cocoa for recent, faded for old
      const daysSince = node.lastDate
        ? (Date.now() - new Date(node.lastDate).getTime()) / 86400000
        : 30;
      const recency = Math.max(0.3, 1 - daysSince / 60);

      ctx.globalAlpha = node.opacity;

      // Glow
      const gradient = ctx.createRadialGradient(
        node.x, node.y, node.radius * 0.2,
        node.x, node.y, node.radius * 1.8,
      );
      gradient.addColorStop(0, `rgba(145, 109, 101, ${0.15 * recency})`);
      gradient.addColorStop(1, 'rgba(145, 109, 101, 0)');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius * 1.8, 0, Math.PI * 2);
      ctx.fill();

      // Node circle
      ctx.fillStyle = `rgba(145, 109, 101, ${0.6 + 0.4 * recency})`;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();

      // Inner highlight
      ctx.fillStyle = `rgba(191, 168, 197, ${0.3 * recency})`;
      ctx.beginPath();
      ctx.arc(node.x - node.radius * 0.2, node.y - node.radius * 0.2, node.radius * 0.4, 0, Math.PI * 2);
      ctx.fill();

      // Label
      ctx.globalAlpha = node.opacity * 0.9;
      ctx.fillStyle = '#5A4A44';
      ctx.font = `${Math.max(9, Math.min(12, node.radius * 0.7))}px var(--font-sans)`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const label = node.id.length > 12 ? node.id.slice(0, 11) + '..' : node.id;
      ctx.fillText(label, node.x, node.y + node.radius + 12);
    }

    ctx.globalAlpha = 1;
    frameRef.current = requestAnimationFrame(simulate);
  }, []);

  useEffect(() => {
    if (isMobile || !skills.length) return;

    // Set revealed nodes' opacity
    const nodes = nodesRef.current;
    for (let i = 0; i < nodes.length; i++) {
      if (i < revealed) {
        nodes[i].opacity = Math.max(nodes[i].opacity, 0.01);
      }
    }

    frameRef.current = requestAnimationFrame(simulate);
    return () => cancelAnimationFrame(frameRef.current);
  }, [revealed, isMobile, skills.length, simulate]);

  if (!skills.length) {
    return (
      <div className="animate-fade-in-up" style={{ animationDelay: '300ms', animationFillMode: 'backwards' }}>
        <span className="text-[11px] font-medium uppercase tracking-widest text-neutral-400">
          Evidence Density
        </span>
        <p className="mt-3 text-sm text-neutral-400">
          Complete missions and log evidence to build your skill constellation.
        </p>
      </div>
    );
  }

  // Mobile fallback: horizontal bar chart
  if (isMobile) {
    const maxCount = Math.max(...skills.map(s => s.count), 1);
    return (
      <div className="animate-fade-in-up" style={{ animationDelay: '300ms', animationFillMode: 'backwards' }}>
        <span className="text-[11px] font-medium uppercase tracking-widest text-neutral-400">
          Evidence Density
        </span>
        <div className="mt-3 space-y-2">
          {skills.slice(0, 12).map(s => (
            <div key={s.skill} className="flex items-center gap-3">
              <span className="w-24 shrink-0 truncate text-xs text-neutral-600">{s.skill}</span>
              <div className="relative h-3 flex-1 rounded-full bg-surface-3 overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-primary-400 transition-all duration-500"
                  style={{ width: `${(s.count / maxCount) * 100}%` }}
                />
              </div>
              <span className="w-6 shrink-0 text-right text-xs font-mono tabular-nums text-neutral-400">
                {s.count}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in-up" style={{ animationDelay: '300ms', animationFillMode: 'backwards' }}>
      <span className="text-[11px] font-medium uppercase tracking-widest text-neutral-400">
        Evidence Density
      </span>
      <div className="mt-3 flex justify-center">
        <canvas
          ref={canvasRef}
          width={400}
          height={300}
          className="w-full max-w-[400px]"
          aria-label={`Skill constellation showing ${skills.length} documented skills`}
          role="img"
        />
      </div>
    </div>
  );
}
