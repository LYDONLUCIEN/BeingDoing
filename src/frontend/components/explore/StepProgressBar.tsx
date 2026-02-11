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
}

export default function StepProgressBar({
  steps,
  currentStep,
  onStepChange,
  progressByStep = {},
}: StepProgressBarProps) {
  const [hoverStep, setHoverStep] = useState<string | null>(null);
  const sorted = [...steps].sort((a, b) => a.order - b.order);

  return (
    <div className="w-full relative">
      <div className="flex items-center gap-0 rounded-full overflow-hidden bg-white/5 border border-white/10">
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
                (isActive ? 'bg-primary-500/90 text-white' : '') +
                (isCompleted && !isActive ? ' bg-white/10 text-white/80' : '') +
                (!isActive && !isCompleted ? ' bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/90' : '')
              }
              title={step.description}
            >
              <span className="truncate block">{step.name}</span>
            </button>
          );
        })}
      </div>
      {hoverStep && (
        <div className="absolute z-10 mt-2 px-3 py-2 rounded-lg bg-slate-800/95 border border-white/10 text-white/90 text-sm shadow-xl max-w-xs pointer-events-none">
          {sorted.find((s) => s.id === hoverStep)?.description}
        </div>
      )}
    </div>
  );
}
