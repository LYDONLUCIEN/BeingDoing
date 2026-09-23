'use client';

/**
 * guided 布局左栏：方向组合列表（复刻 HTML openlife-journey (21).html guided 布局的 sidebar）
 *
 * 结构口径：左侧「新建组合 + 组合列表」，右侧选择器，中间对话在组合确认后解锁。
 * 数据与 TopComboBar 同源（ruminationV4Store.state.combo_sessions）：
 * - 「＋ 新建组合」= 进入草稿态（active_combo_id=null + main_section='matrix'，与 TopComboBar 一致）
 * - 点击行切换组合（switchCombo）；hover 出现删除（二次确认，至少保留一个）
 * - 终选已提交后整列只读（不渲染新建/删除），入选组合加紫色描边环
 *
 * 2026-09-23 结构对齐前四阶段：本栏直接挂在页面根级（全高、右边线分隔的扁平左栏，
 * 同 HTML .sidebar / 前四阶段会话侧栏），不再是被 outer-shell 包住的浮动圆角卡；
 * 无 blur——流光背景直接透过 0.45 白度可见。
 * chips 用 duo 色呼应选择矩阵（热爱珊瑚浅底 × 优势雾蓝浅底）。
 */

import { useState } from 'react';
import { PenLine, Plus, Trash2 } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import type { ComboSession } from '@/lib/explore/ruminationV4Api';

const MAX_COMBOS = 10;

interface SidebarProps {
  /** 点「编辑」展开右侧选择器（结论卡完整编辑入口在那边），由 RuminationV4Page 注入 */
  onExpandSelector?: () => void;
}

/** 与 TopComboBar.enterDraft 同口径：清空 active 组合，回到选择器草稿 */
export function enterComboDraft() {
  useRuminationV4Store.setState((s) => ({
    state: s.state ? { ...s.state, active_combo_id: null, main_section: 'matrix' } : s.state,
  }));
}

/** 状态 meta 行：结论 > 搁置 > 轮次（assistant 消息数；state 未带 messages 时仅显示状态） */
function comboMetaText(c: ComboSession): string {
  if (c.conclusion_card || c.status === 'concluded') return '已有结论';
  if (c.status === 'abandoned') return '已搁置';
  const rounds = (c.messages || []).filter((m) => m.role === 'assistant').length;
  return rounds > 0 ? `探讨中 · ${rounds} 轮` : '待探索';
}

/** 结论 hypothesis 转纯文本（防御旧 dict 形态），供底部摘要 */
function hypText(c: ComboSession | undefined): string {
  const h = c?.conclusion_card?.hypothesis;
  if (!h) return '';
  if (typeof h === 'string') return h;
  return Object.values(h).filter(Boolean).join('\n');
}

export default function V4ComboSidebar({ onExpandSelector }: SidebarProps) {
  const { state, switchCombo, removeCombo } = useRuminationV4Store();
  const [confirmId, setConfirmId] = useState<string | null>(null);

  if (!state) return null;
  const combos = state.combo_sessions || [];
  const activeId = state.active_combo_id ?? null;
  const activeCombo = combos.find((c) => c.combo_id === activeId);
  const activeSummary = hypText(activeCombo);
  const finalSubmitted = !!state.final_selection?.submitted;
  const finalSelectedIds = new Set(state.final_selection?.selected_combo_ids || []);
  const atLimit = combos.length >= MAX_COMBOS;

  return (
    <aside
      className="v4-combo-sidebar relative z-10 flex min-h-0 w-[238px] shrink-0 flex-col border-r border-[rgba(100,91,122,0.1)] bg-white/45 py-4 pl-4 pr-3.5"
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
          className="mb-2 flex min-h-[40px] shrink-0 items-center justify-center gap-1.5 rounded-full bg-[var(--journey-ink,#17212d)] px-4 text-[13px] font-semibold text-white transition-all hover:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus size={14} strokeWidth={2.2} aria-hidden /> 新建组合
        </button>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
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
              className={`group relative flex min-h-[74px] shrink-0 cursor-pointer flex-col gap-1.5 rounded-[14px] border px-3 pb-2.5 pt-2 text-left outline-none transition-all focus-visible:ring-2 focus-visible:ring-[#886ddc]/40 ${
                isActive
                  ? 'border-[rgba(111,82,199,0.4)] bg-white/95 shadow-[0_5px_15px_rgba(31,26,58,0.07)]'
                  : 'border-transparent bg-white/40 hover:bg-white/70'
              }`}
              style={
                isFinalSelected
                  ? { boxShadow: '0 0 0 1.5px rgba(122,100,255,0.55), 0 4px 15px rgba(19,38,76,0.06)' }
                  : undefined
              }
            >
              <span
                className={`text-[11px] font-bold leading-none tracking-[0.07em] ${
                  isActive ? 'text-[#6f52c7]' : 'text-[#9aa4b2]'
                }`}
              >
                {String(idx + 1).padStart(2, '0')}
              </span>

              {/* chips 直出（0923 拍板换紫系）：热爱 = 实底紫（组合的主词条），优势 = 浅紫底，
                  统一锚定沉淀阶段主色，不再与矩阵的珊瑚/雾蓝双色竞争 */}
              <div className="flex flex-wrap content-start items-start gap-1 pr-4">
                <span className="inline-flex max-w-full items-center truncate rounded-[6px] bg-[#6f52c7] px-1.5 py-0.5 text-[11px] font-medium leading-snug text-white">
                  {c.passion}
                </span>
                {c.strengths.map((s) => (
                  <span
                    key={s}
                    className="inline-flex max-w-full items-center truncate rounded-[6px] border border-[#ddd3f3] bg-[#f1edfb] px-1.5 py-0.5 text-[11px] leading-snug text-[#5b3fb8]"
                  >
                    {s}
                  </span>
                ))}
              </div>

              <span className="text-[11px] leading-none text-[#959fab]">
                {comboMetaText(c)}
                {isFinalSelected && <span className="ml-1 text-[#886ddc]">· 已入选</span>}
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
                <span className="absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-[14px] bg-white/95">
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

      {/* 下段（0923 拍板）：固定占侧栏下 1/3、高度不变的结论摘要区——只读、可独立滚动浏览全文，
          上段组合列表同样可滚动；「编辑」展开右侧选择器做完整编辑 */}
      <div className="flex h-1/3 min-h-[120px] shrink-0 flex-col border-t border-[rgba(100,91,122,0.12)] pt-2.5">
        <div className="flex shrink-0 items-center justify-between px-1 pb-1.5">
          <span className="text-[11px] font-semibold tracking-[0.06em] text-[#929aa5]">
            当前结论
          </span>
          {activeSummary && onExpandSelector && !finalSubmitted && (
            <button
              type="button"
              onClick={onExpandSelector}
              title="在右侧选择器中编辑结论卡"
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold text-[#6f52c7] transition-colors hover:bg-[#f3f0fc] hover:text-[#886ddc]"
            >
              <PenLine size={11} strokeWidth={2.2} aria-hidden /> 编辑
            </button>
          )}
        </div>
        {activeSummary ? (
          <div
            className={`min-h-0 flex-1 overflow-y-auto rounded-[10px] border border-[rgba(100,91,122,0.1)] bg-white/70 px-2.5 py-2 text-[12px] leading-[1.65] text-[#4b5563] ${
              activeCombo?.user_skipped ? 'text-[#9aa4b2] line-through' : ''
            }`}
          >
            <span className="whitespace-pre-wrap">{activeSummary}</span>
          </div>
        ) : (
          <p className="m-0 min-h-0 flex-1 overflow-y-auto px-1 text-[11.5px] leading-relaxed text-[#9aa4b2]">
            {activeCombo
              ? '这个组合还没有结论，聊完后在结论卡里确认'
              : '选择一个组合后，这里显示它的结论摘要'}
          </p>
        )}
      </div>
    </aside>
  );
}
