'use client';

/**
 * v4 左栏：选择器网格 + 当前结论卡
 * 视觉对齐 new-rumination-v4.html：选择器与结论卡共用同一个毛玻璃外壳，
 * 内部仅通过轻微背景/边框区分 panel。
 */

import { useMemo, useState, type CSSProperties } from 'react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import V4ComboMatrixSelector from './V4ComboMatrixSelector';
import ConclusionCardEditable from './ConclusionCardEditable';

const selectionPanelStyle: CSSProperties = {
  borderRadius: '16px',
  border: '1px solid rgba(118,135,192,0.09)',
  background: 'rgba(255,255,255,0.46)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.65)',
  padding: '16px 16px 14px',
};

const conclusionPanelStyle: CSSProperties = {
  borderRadius: '16px',
  border: '1px solid rgba(118,135,192,0.09)',
  background: 'rgba(255,255,255,0.46)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.65)',
  padding: '14px 16px 12px',
};

export default function V4MatrixLeftPanel({ stacked = false }: { stacked?: boolean }) {
  const { state, createAndStart, comboCache, error, clearError } = useRuminationV4Store();
  const [creating, setCreating] = useState(false);

  const activeCombo = useMemo(() => {
    if (!state?.active_combo_id) return null;
    const id = state.active_combo_id;
    const fromSessions = state.combo_sessions.find((c) => c.combo_id === id);
    return fromSessions || comboCache[id] || null;
  }, [state?.active_combo_id, state?.combo_sessions, comboCache]);

  if (!state) return null;
  const passions = state.matrix_snapshot.passions || [];
  const strengths = state.matrix_snapshot.strengths || [];

  const isLocked = !!activeCombo;
  const conclusionCard = activeCombo?.conclusion_card || null;

  const handleCreate = async (passion: string, selectedStrengths: string[]) => {
    clearError();
    setCreating(true);
    try {
      const id = await createAndStart(passion, selectedStrengths);
      return !!id;
    } finally {
      setCreating(false);
    }
  };

  return (
    <div
      className={`flex flex-col gap-2.5 ${stacked ? 'h-auto' : 'h-full min-h-0 overflow-hidden'}`}
    >
      {error && (
        <div
          className="shrink-0 rounded-xl px-3 py-2 text-[12px] font-[650] leading-snug text-red-700"
          style={{
            background: 'rgba(254,226,226,0.9)',
            border: '1px solid rgba(248,113,113,0.35)',
          }}
          role="alert"
        >
          <div className="flex items-start justify-between gap-2">
            <span>{error}</span>
            <button
              type="button"
              className="shrink-0 text-[11px] text-red-500 underline"
              onClick={() => clearError()}
            >
              关闭
            </button>
          </div>
        </div>
      )}

      {/* 选择器面板：双栏模式下空间不足时允许收缩并内部滚动（修复低高度视口裁切），堆叠模式下自然高度由页面滚动承载 */}
      <div
        className={stacked ? 'shrink-0' : 'min-h-0 shrink overflow-y-auto rumination-hyp-preview-scroll'}
        style={selectionPanelStyle}
      >
        <V4ComboMatrixSelector
          passions={passions}
          strengths={strengths}
          onCreateCombo={handleCreate}
          creating={creating}
          locked={isLocked}
          lockedPassion={activeCombo?.passion || null}
          lockedStrengths={activeCombo?.strengths || []}
        />
      </div>

      <div
        className={`flex flex-col ${stacked ? 'flex-none' : 'min-h-0 flex-1 overflow-hidden'}`}
      >
        <div
          className="flex min-h-0 flex-1 flex-col overflow-y-auto rumination-hyp-preview-scroll"
          style={conclusionPanelStyle}
        >
          <div className="mb-2 flex shrink-0 items-center gap-2 px-1">
            <span className="text-[14px] font-[760] text-[#4b5563]">结论卡</span>
            {activeCombo && (
              <span className="text-[12px] font-[500] text-[#9ca3af]">
                {activeCombo.passion}
              </span>
            )}
          </div>

          {!activeCombo ? (
            <div className="flex flex-1 items-center justify-center px-4 py-6 text-center text-[13px] font-[700] text-[#9ca3af]">
              选择热爱与优势后，点击「开始探索」
            </div>
          ) : (
            // ADR-0015:结论卡常驻左栏,一开始就是空卡槽,由用户手填
            <ConclusionCardEditable
              comboId={activeCombo.combo_id}
              card={conclusionCard}
              analysis={activeCombo.balance_analysis || null}
              userSkipped={!!activeCombo.user_skipped || activeCombo.status === 'abandoned'}
            />
          )}
        </div>
      </div>
    </div>
  );
}
