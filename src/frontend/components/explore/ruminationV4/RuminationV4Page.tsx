'use client';

/**
 * Rumination v4 页壳
 *
 * 一个大容器内：顶栏（居中「05 沉淀」+ 右上「完成并继续」）
 * → 组合 tabs +「新建组合」
 * → 左选择器/结论 + 右对话（内部分区）
 */

import { useEffect, useState, type CSSProperties } from 'react';
import dynamic from 'next/dynamic';
import { FileText } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import V4ChatPanel from './V4ChatPanel';
import TopComboBar from './TopComboBar';
import V4FinalSelectionModal from './V4FinalSelectionModal';

const ExploreLandingMeshLayers = dynamic(
  () => import('@/components/explore/ExploreLandingMeshLayers'),
  { ssr: false }
);
const V4MatrixLeftPanel = dynamic(() => import('./V4MatrixLeftPanel'), { ssr: false });

interface Props {
  activationCode: string;
  onCompleteAndContinue?: () => void;
  canContinue?: boolean;
  continueDisabledHint?: string;
}

const outerShellStyle: CSSProperties = {
  borderRadius: '28px',
  border: '1px solid rgba(255,255,255,0.72)',
  background: 'rgba(255,255,255,0.42)',
  boxShadow: '0 16px 40px rgba(33,48,79,0.08)',
  backdropFilter: 'blur(18px)',
  padding: '14px 16px 16px',
};

const innerPaneStyle: CSSProperties = {
  borderRadius: '18px',
  border: '1px solid rgba(255,255,255,0.42)',
  background: 'rgba(255,255,255,0.36)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.55)',
  padding: '12px',
};

export default function RuminationV4Page({
  activationCode,
  onCompleteAndContinue,
  canContinue = true,
  continueDisabledHint = '',
}: Props) {
  const { state, init } = useRuminationV4Store();
  const [finalModalOpen, setFinalModalOpen] = useState(false);

  useEffect(() => {
    if (activationCode) {
      init(activationCode);
    }
  }, [activationCode, init]);

  useEffect(() => {
    if (state?.active_combo_id) {
      useRuminationV4Store.getState().loadCombo(state.active_combo_id);
    }
  }, [state?.active_combo_id]);

  const v4CanContinue =
    canContinue ||
    !!state?.final_selection?.submitted ||
    (state?.combo_sessions || []).some(
      (c) => !!c.conclusion_card || c.status === 'concluded'
    );

  if (!state) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-[#9ca3af]">
        加载中…
      </div>
    );
  }

  return (
    <div
      className="rumination-beautiful-root flow-light relative flex min-h-0 flex-1 overflow-hidden"
      data-phase="rumination"
    >
      <ExploreLandingMeshLayers />

      <div className="relative z-10 flex min-h-0 w-full flex-col px-3 pb-3 pt-1 sm:px-4">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden" style={outerShellStyle}>
          {/* 顶栏：居中标题 + 右上完成并继续 */}
          <header className="hero mb-2.5 grid shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-[rgba(80,94,145,0.08)] pb-3 pt-1 text-center">
            <div />
            <div className="px-4 sm:px-8">
              <h1 className="m-0 text-[26px] font-[850] leading-tight tracking-wide text-[#1f2a44] sm:text-[42px]">
                05 沉淀
                <span className="ml-2 inline-block text-[#ff987b]" style={{ fontSize: '0.85em' }}>
                  ✦
                </span>
              </h1>
              <p className="mx-auto mt-2 max-w-[520px] text-[13px] font-[500] leading-relaxed text-[#657198] sm:text-[16px]">
                把热爱与优势组成方向，和 AI 深入聊一聊，留下你的假设结论
              </p>
            </div>
            <div className="flex justify-end pr-1">
              {onCompleteAndContinue && (
                <button
                  type="button"
                  onClick={() => setFinalModalOpen(true)}
                  disabled={!v4CanContinue}
                  title={continueDisabledHint || undefined}
                  className="complete-btn flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-bold text-white transition-all hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 sm:px-5 sm:py-3 sm:text-base"
                  style={{
                    background: 'linear-gradient(180deg,#121f3f,#07132f)',
                    boxShadow: '0 10px 22px rgba(4,19,52,0.22)',
                  }}
                >
                  <FileText size={18} strokeWidth={2} className="hidden shrink-0 sm:inline" />
                  <span className="max-w-[7.5rem] truncate sm:max-w-none">完成并继续</span>
                </button>
              )}
            </div>
          </header>

          {/* 组合 tabs + 新建组合 */}
          <div className="mb-2.5 min-w-0 shrink-0">
            <TopComboBar />
          </div>

          {/* 左选择器 / 右对话 */}
          <div className="rumination-workbench flex min-h-0 flex-1 gap-3 overflow-hidden">
            <div
              className="flex min-h-0 min-w-0 flex-[1.05] flex-col overflow-hidden"
              style={{ ...innerPaneStyle, padding: 0 }}
            >
              <V4MatrixLeftPanel />
            </div>
            <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
              <V4ChatPanel comboId={state.active_combo_id} />
            </div>
          </div>
        </div>
      </div>

      <V4FinalSelectionModal
        open={finalModalOpen}
        onClose={() => setFinalModalOpen(false)}
        onConfirm={() => {
          setFinalModalOpen(false);
          onCompleteAndContinue?.();
        }}
      />
    </div>
  );
}
