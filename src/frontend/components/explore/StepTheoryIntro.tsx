'use client';

import { useSpring, animated, config } from '@react-spring/web';
import { Sparkles, ArrowRight } from 'lucide-react';

interface StepTheoryIntroProps {
  stepName: string;
  purpose: string;
  theory: string;
  onStart: () => void;
}

export default function StepTheoryIntro({
  stepName,
  purpose,
  theory,
  onStart,
}: StepTheoryIntroProps) {
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
            <div className="absolute inset-0 bg-primary-500/20 rounded-full blur-2xl animate-pulse" />
            <div className="relative p-4 rounded-full bg-gradient-to-br from-primary-500/30 to-primary-600/20 border border-primary-500/30">
              <Sparkles className="w-12 h-12 text-primary-400" />
            </div>
          </div>
        </div>

        {/* Title */}
        <animated.div style={titleSpring} className="text-center space-y-3">
          <h1 className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-primary-300 via-primary-200 to-primary-300 bg-clip-text text-transparent">
            {stepName}
          </h1>
          <p className="text-xl text-white/80">{purpose}</p>
        </animated.div>

        {/* Theory Content */}
        <animated.div
          style={contentSpring}
          className="bg-gradient-to-br from-white/10 to-white/5 backdrop-blur-sm rounded-2xl p-6 md:p-8 border border-white/10 shadow-2xl"
        >
          <div className="prose prose-invert prose-lg max-w-none">
            {theory.split('\n').map((paragraph, idx) => (
              paragraph.trim() && (
                <p key={idx} className="text-white/80 leading-relaxed mb-4 last:mb-0">
                  {paragraph}
                </p>
              )
            ))}
          </div>
        </animated.div>

        {/* Start Button */}
        <animated.div style={buttonSpring} className="flex justify-center pt-4">
          <button
            type="button"
            onClick={onStart}
            className="group relative px-8 py-4 rounded-xl bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-400 hover:to-primary-500 text-white font-semibold text-lg shadow-lg hover:shadow-primary-500/50 transition-all transform hover:scale-105 active:scale-95"
          >
            <span className="flex items-center gap-2">
              开始探索
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </span>
            {/* Glow effect */}
            <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-primary-400/0 via-white/20 to-primary-400/0 opacity-0 group-hover:opacity-100 transition-opacity blur-xl" />
          </button>
        </animated.div>

        {/* Decorative elements */}
        <div className="flex justify-center gap-2 pt-4">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="w-2 h-2 rounded-full bg-primary-500/30"
              style={{
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
