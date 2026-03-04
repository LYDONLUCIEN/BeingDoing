'use client';

import { useSpring, animated, config } from '@react-spring/web';
import { Sparkles, ArrowRight } from 'lucide-react';

interface StepTheoryIntroProps {
  stepName: string;
  purpose: string;
  theory: string;
  onStart: () => void;
  /** light: 浅色主题（flow 对话页） */
  variant?: 'dark' | 'light';
}

export default function StepTheoryIntro({
  stepName,
  purpose,
  theory,
  onStart,
  variant = 'dark',
}: StepTheoryIntroProps) {
  const isLight = variant === 'light';
  // 标题动画
  const titleSpring = useSpring({
    from: { opacity: 0, transform: 'translateY(-20px)' },
    to: { opacity: 1, transform: 'translateY(0px)' },
    config: config.gentle,
    delay: 100,
  });

  // 内容动画
  const contentSpring = useSpring({
    from: { opacity: 0, transform: 'translateY(20px)' },
    to: { opacity: 1, transform: 'translateY(0px)' },
    config: config.gentle,
    delay: 300,
  });

  // 按钮动画
  const buttonSpring = useSpring({
    from: { opacity: 0, transform: 'scale(0.9)' },
    to: { opacity: 1, transform: 'scale(1)' },
    config: config.wobbly,
    delay: 500,
  });

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <div className="space-y-8">
        {/* Icon */}
        <div className="flex justify-center">
          <div className="relative">
            <div
              className={`absolute inset-0 rounded-full blur-2xl animate-pulse ${
                isLight ? 'bg-[var(--bd-ui-accent)]/25' : 'bg-primary-500/20'
              }`}
            />
            <div
              className={`relative p-4 rounded-full border ${
                isLight
                  ? 'bg-[var(--bd-ui-accent)]/15 border-[var(--bd-ui-accent)]/30'
                  : 'bg-gradient-to-br from-primary-500/30 to-primary-600/20 border-primary-500/30'
              }`}
            >
              <Sparkles
                className={`w-12 h-12 ${isLight ? 'text-[var(--bd-ui-accent)]' : 'text-primary-400'}`}
              />
            </div>
          </div>
        </div>

        {/* Title */}
        <animated.div style={titleSpring} className="text-center space-y-3">
          <h1
            className={
              isLight
                ? 'text-3xl md:text-4xl font-bold bg-gradient-to-r from-[var(--bd-ui-accent)] via-purple-500 to-[var(--bd-ui-accent)] bg-clip-text text-transparent'
                : 'text-3xl md:text-4xl font-bold bg-gradient-to-r from-primary-300 via-primary-200 to-primary-300 bg-clip-text text-transparent'
            }
          >
            {stepName}
          </h1>
          <p className={`text-xl ${isLight ? 'text-neutral-600' : 'text-white/80'}`}>{purpose}</p>
        </animated.div>

        {/* Theory Content */}
        <animated.div
          style={contentSpring}
          className={
            isLight
              ? 'bg-white/80 backdrop-blur-sm rounded-2xl p-6 md:p-8 border border-black/6 shadow-lg'
              : 'bg-gradient-to-br from-white/10 to-white/5 backdrop-blur-sm rounded-2xl p-6 md:p-8 border border-white/10 shadow-2xl'
          }
        >
          <div className={`prose prose-lg max-w-none ${isLight ? '' : 'prose-invert'}`}>
            {theory.split('\n').map((paragraph, idx) => (
              paragraph.trim() && (
                <p
                  key={idx}
                  className={`leading-relaxed mb-4 last:mb-0 ${isLight ? 'text-neutral-600' : 'text-white/80'}`}
                >
                  {paragraph}
                </p>
              )
            ))}
          </div>
        </animated.div>

        {/* Start Button - 紫色系 */}
        <animated.div style={buttonSpring} className="flex justify-center pt-4">
          <button
            type="button"
            onClick={onStart}
            className="group relative px-8 py-4 rounded-xl text-white font-semibold text-lg shadow-lg transition-all transform hover:scale-105 active:scale-95"
            style={{ background: 'var(--bd-ui-accent)' }}
          >
            <span className="flex items-center gap-2">
              开始探索
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </span>
          </button>
        </animated.div>

        {/* Decorative elements */}
        <div className="flex justify-center gap-2 pt-4">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className={`w-2 h-2 rounded-full ${!isLight ? 'bg-primary-500/30' : ''}`}
              style={{
                ...(isLight && { background: 'rgba(167,139,250,0.4)' }),
                animation: `pulse 2s ease-in-out infinite ${i * 0.2}s`,
              }}
            />
          ))}
        </div>
      </div>

      <style jsx>{`
        @keyframes pulse {
          0%, 100% {
            opacity: 0.3;
            transform: scale(1);
          }
          50% {
            opacity: 1;
            transform: scale(1.2);
          }
        }
      `}</style>
    </div>
  );
}
