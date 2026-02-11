'use client';

import Link from 'next/link';
import StepProgressBar from './StepProgressBar';
import { ArrowLeft, Bug } from 'lucide-react';
import { FLOW_STEPS } from '@/lib/constants';

interface FlowHeaderProps {
  currentStep: string;
  progressByStep: Record<string, { percentage: number }>;
  isSuperAdmin: boolean;
  onStepChange: (step: string) => void;
  onOpenDebug: () => void;
}

export default function FlowHeader({
  currentStep,
  progressByStep,
  isSuperAdmin,
  onStepChange,
  onOpenDebug,
}: FlowHeaderProps) {
  return (
    <header className="flex-shrink-0 border-b border-white/10 bg-slate-900/80 backdrop-blur px-4 py-3">
      <div className="max-w-4xl mx-auto flex items-center justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3 mb-3">
            <Link
              href="/explore"
              className="flex items-center gap-1 text-sm text-white/60 hover:text-white transition-colors"
            >
              <ArrowLeft size={16} /> 返回
            </Link>
            <h1 className="text-lg font-semibold text-white/95">探索流程</h1>
          </div>
          <StepProgressBar
            steps={FLOW_STEPS}
            currentStep={currentStep}
            onStepChange={onStepChange}
            progressByStep={progressByStep}
          />
        </div>
        <div className="flex items-center gap-3">
          {isSuperAdmin && (
            <button
              type="button"
              onClick={onOpenDebug}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/10 text-white/70 hover:bg-white/20 text-sm"
              title="调试（超级管理员可见完整日志）"
            >
              <Bug size={16} /> 调试
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
