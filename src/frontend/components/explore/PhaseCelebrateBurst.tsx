'use client';

import { useEffect, useRef } from 'react';

/**
 * 庆祝粒子层：与 uidesign/beautiful/celebration-particles.html 中 canvas 逻辑一致。
 * 依赖 playSignal 递增触发；无文案（阶段完成 copy 由 PhaseCompleteWarmModal 负责）。
 */
export type PhaseCelebrateBurstProps = {
  /** 每次完成探索时由父组件递增，用于重播 */
  playSignal: number;
  className?: string;
};

const CELEBRATION_COLORS = ['#10b981', '#3b82f6', '#a78bfa', '#f59e0b', '#f472b6'];
const PARTICLE_COUNT = 40;

export default function PhaseCelebrateBurst({ playSignal, className = '' }: PhaseCelebrateBurstProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (playSignal <= 0) return;

    const stage = stageRef.current;
    const canvas = canvasRef.current;
    if (!stage || !canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number | null = null;

    const fitCanvas = () => {
      const rect = stage.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
    };

    const colors = CELEBRATION_COLORS;
    const particles: {
      x: number;
      y: number;
      r: number;
      speed: number;
      wobble: number;
      wobbleSpeed: number;
      color: string;
      alpha: number;
      delay: number;
      born: number;
    }[] = [];

    fitCanvas();

    const w = canvas.width;
    const h = canvas.height;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * w,
        y: h + Math.random() * 40,
        r: 2 + Math.random() * 4,
        speed: 0.4 + Math.random() * 1.2,
        wobble: Math.random() * Math.PI * 2,
        wobbleSpeed: 0.01 + Math.random() * 0.03,
        color: colors[Math.floor(Math.random() * colors.length)]!,
        alpha: 0.3 + Math.random() * 0.5,
        delay: Math.random() * 1200,
        born: performance.now(),
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const now = performance.now();
      let alive = false;

      for (const p of particles) {
        const age = now - p.born;
        if (age < p.delay) {
          alive = true;
          continue;
        }

        p.y -= p.speed;
        p.wobble += p.wobbleSpeed;
        const ox = Math.sin(p.wobble) * 12;

        const fade = p.y < canvas.height * 0.15 ? p.y / (canvas.height * 0.15) : 1;
        const a = p.alpha * fade;
        if (a <= 0.01) continue;
        alive = true;

        ctx.beginPath();
        ctx.arc(p.x + ox, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = a;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(p.x + ox, p.y, p.r * 2.5, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = a * 0.15;
        ctx.fill();
      }

      ctx.globalAlpha = 1;
      if (alive) {
        animId = requestAnimationFrame(draw);
      }
    };

    animId = requestAnimationFrame(draw);

    const onResize = () => {
      fitCanvas();
    };
    window.addEventListener('resize', onResize);

    return () => {
      window.removeEventListener('resize', onResize);
      if (animId !== null) cancelAnimationFrame(animId);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [playSignal]);

  return (
    <div
      ref={stageRef}
      className={`pointer-events-none fixed inset-0 z-[200] overflow-hidden ${className}`}
      aria-hidden
    >
      <canvas ref={canvasRef} className="absolute inset-0 block h-full w-full" />
    </div>
  );
}
