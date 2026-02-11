'use client';

import { FLOW_STEPS } from '@/lib/constants';

interface StepIntroSectionProps {
  currentStep: string;
  onStart: () => void;
}

export default function StepIntroSection({ currentStep, onStart }: StepIntroSectionProps) {
  const stepInfo = FLOW_STEPS.find((s) => s.id === currentStep);

  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center space-y-4">
      <h2 className="text-xl font-semibold">
        {stepInfo?.name || '新的探索阶段'}
      </h2>
      <p className="max-w-xl text-sm text-white/70">
        {stepInfo?.description ||
          '这一阶段，我们会围绕一个新的主题展开对话，请根据自己的真实想法慢慢表达。'}
      </p>
      <button
        type="button"
        onClick={onStart}
        className="mt-2 px-5 py-2.5 rounded-lg bg-primary-500 hover:bg-primary-400 text-white text-sm font-medium"
      >
        开始本阶段
      </button>
    </div>
  );
}
