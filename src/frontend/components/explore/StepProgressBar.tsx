'use client';

import { useState } from 'react';

export interface StepItem {
  id: string;
  name: string;
  description: string;
  order: number;
}

interface StepProgressBarProps {
  steps: StepItem[];
  currentStep: string;
  onStepChange: (stepId: string) => void;
  progressByStep?: Record<string, { percentage: number }>;
  variant?: 'dark' | 'light';
}

export default function StepProgressBar({
  steps,
  currentStep,
  onStepChange,
  progressByStep = {},
  variant = 'dark',
}: StepProgressBarProps) {
  const [hoverStep, setHoverStep] = useState<string | null>(null);
  const sorted = [...steps].sort((a, b) => a.order - b.order);
  const isLight = variant === 'light';

  return (
    <div className="w-full relative">
      <div
        className={`flex items-center gap-0 rounded-full overflow-hidden ${
          isLight ? 'bg-neutral-200/60 border-neutral-300/50' : 'bg-white/5 border border-white/10'
        }`}
      >
        {sorted.map((step) => {
          const isActive = step.id === currentStep;
          const isCompleted = (progressByStep[step.id]?.percentage ?? 0) >= 100;

          return (
            <button
              key={step.id}
              type="button"
              onClick={() => onStepChange(step.id)}
              onMouseEnter={() => setHoverStep(step.id)}
              onMouseLeave={() => setHoverStep(null)}
              className={
                'flex-1 min-w-0 py-2.5 px-2 text-center text-sm font-medium transition-all duration-200 ' +
                (isActive
                  ? isLight
                    ? 'bg-[var(--bd-ui-accent)] text-white'
                    : 'bg-primary-500/90 text-white'
                  : '') +
                (isCompleted && !isActive
                  ? isLight
                    ? ' bg-neutral-300/70 text-neutral-700'
                    : ' bg-white/10 text-white/80'
                  : '') +
                (!isActive && !isCompleted
                  ? isLight
                    ? ' text-neutral-600 hover:bg-neutral-300/50 hover:text-neutral-900'
                    : ' bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/90'
                  : '')
              }
              title={step.description}
            >
              <span className="truncate block">{step.name}</span>
            </button>
          );
        })}
      </div>
      {hoverStep && (
        <div
          className={`absolute z-10 mt-2 px-3 py-2 rounded-lg text-sm shadow-xl max-w-xs pointer-events-none ${
            isLight
              ? 'bg-white/95 border border-neutral-200 text-neutral-700'
              : 'bg-slate-800/95 border border-white/10 text-white/90'
          }`}
        >
          {sorted.find((s) => s.id === hoverStep)?.description}
        </div>
      )}
    </div>
  );
}
