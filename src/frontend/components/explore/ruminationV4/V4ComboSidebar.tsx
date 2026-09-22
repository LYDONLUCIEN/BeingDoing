'use client';

/**
 * guided 布局左栏：方向组合列表（复刻 HTML openlife-journey (21).html guided 布局的 sidebar）
 *
 * 结构口径：左侧「新建组合 + 组合列表」，右侧选择器，中间对话在组合确认后解锁。
 * 数据与 TopComboBar 同源（ruminationV4Store.state.combo_sessions）：
 * - 「＋ 新建组合」= 进入草稿态（active_combo_id=null + main_section='matrix'，与 TopComboBar 一致）
 * - 点击行切换组合（switchCombo）；hover 出现删除（二次确认，至少保留一个）
 * - 终选已提交后整列只读（不渲染新建/删除），入选组合加紫色描边环
 */

import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';

const MAX_COMBOS = 10;

/** 与 TopComboBar.enterDraft 同口径：清空 active 组合，回到选择器草稿 */
export function enterComboDraft() {
  useRuminationV4Store.setState((s) => ({
    state: s.state ? { ...s.state, active_combo_id: null, main_section: 'matrix' } : s.state,
  }));
}

export default function V4ComboSidebar() {
  const { state, switchCombo, removeCombo } = useRuminationV4Store();
  const [confirmId, setConfirmId] = useState<string | null>(null);

  if (!state) return null;
  const combos = state.combo_sessions || [];
  const activeId = state.active_combo_id ?? null;
  const finalSubmitted = !!state.final_selection?.submitted;
  const finalSelectedIds = new Set(state.final_selection?.selected_combo_ids || []);
  const atLimit = combos.length >= MAX_COMBOS;

  return (
    <aside
      className="v4-combo-sidebar flex min-h-0 w-[220px] shrink-0 flex-col rounded-[20px] border border-[rgba(100,91,122,0.1)] bg-white/70 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.72),0_10px_28px_rgba(49,43,65,0.04)]"
      aria-label="方向组合列表"
    >
      <p className="m-0 px-1 pb-2 text-[11px] font-semibold tracking-[0.06em] text-[#929aa5]">
        方向组合
      </p>

      {!finalSubmitted && (
        <button
          type="button"
          onClick={enterComboDraft}
          disabled={atLimit}
          title={atLimit ? `最多 ${MAX_COMBOS} 个组合` : '新建一个组合'}
          className="mb-2 flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-xl border border-dashed border-[#c9d4de] bg-white/55 text-[13px] font-semibold text-[#426fa9] transition-colors hover:border-[#5e91e6] hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus size={14} strokeWidth={2.2} aria-hidden /> 新建组合
        </button>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto">
        {combos.length === 0 && (
          <p className="m-0 px-1 pt-2 text-[12px] leading-relaxed text-[#9ca3af]">
            还没有组合，从右侧选择热爱与优势后开始。
          </p>
        )}
        {combos.map((c, idx) => {
          const isActive = c.combo_id === activeId;
          const isFinalSelected = finalSubmitted && finalSelectedIds.has(c.combo_id);
          const isConfirming = confirmId === c.combo_id;
          return (
            <div
              key={c.combo_id}
              role="button"
              tabIndex={0}
              onClick={() => {
                if (isConfirming) return;
                switchCombo(c.combo_id);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  switchCombo(c.combo_id);
                }
              }}
              title={`${c.passion} + ${c.strengths.join('、')}${isFinalSelected ? '（已入选）' : ''}`}
              className={`group relative flex shrink-0 cursor-pointer items-center gap-2 rounded-xl border px-3 py-2.5 text-left transition-all ${
                isActive
                  ? 'border-[#d8e2f0] bg-white/95 shadow-[0_6px_18px_rgba(19,38,76,0.08)]'
                  : 'border-[#e6eaf1] bg-white/55 hover:bg-white/85'
              }`}
              style={
                isFinalSelected
                  ? { boxShadow: '0 0 0 1.5px rgba(122,100,255,0.55), 0 4px 15px rgba(19,38,76,0.06)' }
                  : undefined
              }
            >
              <span
                className={`shrink-0 text-[11px] font-bold ${isActive ? 'text-[#6f52c7]' : 'text-[#9aa4b2]'}`}
              >
                {String(idx + 1).padStart(2, '0')}
              </span>
              <span
                className={`min-w-0 flex-1 truncate text-[12.5px] font-semibold ${
                  isActive ? 'text-[#3d3663]' : 'text-[#45536f]'
                }`}
              >
                {c.passion} × {c.strengths.join('、')}
              </span>

              {/* hover 删除（提交后回看模式不渲染）；二次确认 */}
              {!finalSubmitted && !isConfirming && (
                <button
                  type="button"
                  aria-label="删除组合"
                  title="删除组合"
                  className="absolute right-1.5 top-1/2 hidden h-5 w-5 -translate-y-1/2 place-items-center rounded-full text-[#2e4268] transition-colors hover:bg-[#fff0f0] hover:text-[#ed5163] group-hover:grid"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (combos.length <= 1) return; // 至少保留一个组合
                    setConfirmId(c.combo_id);
                  }}
                >
                  <Trash2 size={12} strokeWidth={2} />
                </button>
              )}
              {isConfirming && (
                <span className="absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-xl bg-white/95">
                  <button
                    type="button"
                    className="rounded-lg bg-[#ef5163] px-2.5 py-1 text-[11px] font-semibold text-white"
                    onClick={async (e) => {
                      e.stopPropagation();
                      await removeCombo(c.combo_id);
                      setConfirmId(null);
                    }}
                  >
                    确认删除
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-[#e1e6ea] px-2.5 py-1 text-[11px] text-[#66727f]"
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmId(null);
                    }}
                  >
                    取消
                  </button>
                </span>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
