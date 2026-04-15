'use client';

import type { CSSProperties } from 'react';

/**
 * 无状态庆祝动效层：仅依赖外部 playSignal 变化触发重挂载后播放 CSS 动画。
 * 替换动效时只改本文件即可；不包含任何文案。
 */
export type PhaseCelebrateBurstProps = {
  /** 每次完成探索时由父组件递增，用于重播 */
  playSignal: number;
  className?: string;
};

export default function PhaseCelebrateBurst({ playSignal, className = '' }: PhaseCelebrateBurstProps) {
  return (
    <div
      key={playSignal}
      className={`pointer-events-none fixed inset-0 z-[200] overflow-hidden ${className}`}
      aria-hidden
    >
      <style>{`
        @keyframes bd-celebrate-float {
          0% { transform: translate3d(0, 0, 0) scale(0.6); opacity: 0; }
          12% { opacity: 0.95; }
          100% { transform: translate3d(var(--dx), -100vh, 0) scale(1); opacity: 0; }
        }
        @keyframes bd-celebrate-glow {
          0% { transform: scale(0.85); opacity: 0.35; }
          40% { transform: scale(1.05); opacity: 0.55; }
          100% { transform: scale(1.2); opacity: 0; }
        }
        .bd-celebrate-orb {
          position: absolute;
          border-radius: 50%;
          filter: blur(0.5px);
          animation: bd-celebrate-float 2.4s cubic-bezier(0.22, 0.82, 0.28, 1) forwards;
        }
        .bd-celebrate-glow-ring {
          position: absolute;
          left: 50%;
          top: 42%;
          width: min(72vw, 420px);
          height: min(72vw, 420px);
          margin-left: calc(min(72vw, 420px) / -2);
          margin-top: calc(min(72vw, 420px) / -2);
          border-radius: 50%;
          background: radial-gradient(
            circle,
            rgba(16, 185, 129, 0.14) 0%,
            rgba(253, 224, 71, 0.06) 38%,
            transparent 68%
          );
          animation: bd-celebrate-glow 2.2s ease-out forwards;
          pointer-events: none;
        }
      `}</style>
      <div className="bd-celebrate-glow-ring" />
      {Array.from({ length: 14 }).map((_, i) => {
        const left = 8 + ((i * 37) % 84);
        const delay = (i % 7) * 0.09;
        const size = 5 + (i % 5) * 2.5;
        const dx = -35 + (i * 23) % 70;
        const hues = [
          'rgba(16, 185, 129, 0.55)',
          'rgba(52, 211, 153, 0.5)',
          'rgba(250, 204, 21, 0.45)',
          'rgba(253, 230, 138, 0.5)',
          'rgba(255, 255, 255, 0.65)',
        ];
        const bg = hues[i % hues.length];
        const orbStyle = {
          left: `${left}%`,
          bottom: '-4vh',
          width: size,
          height: size,
          background: `radial-gradient(circle at 30% 30%, ${bg}, transparent 75%)`,
          boxShadow: `0 0 ${size * 1.2}px ${bg}`,
          animationDelay: `${delay}s`,
          '--dx': `${dx}px`,
        } as CSSProperties;
        return <span key={i} className="bd-celebrate-orb" style={orbStyle} />;
      })}
    </div>
  );
}
