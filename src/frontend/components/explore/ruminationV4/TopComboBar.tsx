'use client';

/**
 * v4 组合 tab 条 — 可水平滑动 +「新建组合」
 *
 * tabs 用固定最小宽度 + overflow-x 滚动，不再 flex-1 均分（否则多 tab 挤成两格看不到更多）。
 */

import { useRef, useState, type WheelEvent } from 'react';
import { Plus } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';

const MAX_COMBOS = 10;

export default function TopComboBar() {
  const { state, switchCombo, removeCombo } = useRuminationV4Store();
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  if (!state) return null;

  const combos = state.combo_sessions || [];
  const activeId = state.active_combo_id;
  const atLimit = combos.length >= MAX_COMBOS;
  const isDraft = !activeId;

  const handleConfirmDelete = async (comboId: string) => {
    await removeCombo(comboId);
    setConfirmId(null);
  };

  const enterDraft = () => {
    useRuminationV4Store.setState((s) => ({
      state: s.state
        ? { ...s.state, active_combo_id: null, main_section: 'matrix' }
        : s.state,
    }));
  };

  /** 触控板/鼠标滚轮纵向滚动时转为横向滑动 */
  const onWheel = (e: WheelEvent<HTMLDivElement>) => {
    const el = scrollerRef.current;
    if (!el) return;
    if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
    if (el.scrollWidth <= el.clientWidth) return;
    e.preventDefault();
    el.scrollLeft += e.deltaY;
  };

  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <div
        ref={scrollerRef}
        onWheel={onWheel}
        className="flex min-w-0 flex-1 items-stretch overflow-x-auto overflow-y-hidden"
        style={{
          height: '48px',
          borderRadius: '14px',
          background: 'rgba(255,255,255,0.55)',
          border: '1px solid rgba(255,255,255,0.44)',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.55), 0 6px 16px rgba(33,48,79,0.05)',
          backdropFilter: 'blur(12px)',
          scrollbarWidth: 'thin',
          WebkitOverflowScrolling: 'touch',
        }}
      >
        {combos.length === 0 && (
          <div className="flex shrink-0 items-center px-4 text-[12px] text-[#9ca3af]">
            还没有组合，选完后点「开始探索」
          </div>
        )}
        {combos.map((c, idx) => {
          const isActive = c.combo_id === activeId;
          const isConfirming = confirmId === c.combo_id;
          return (
            <button
              key={c.combo_id}
              type="button"
              onClick={() => {
                if (isConfirming) return;
                if (confirmId) setConfirmId(null);
                switchCombo(c.combo_id);
              }}
              onContextMenu={(e) => {
                e.preventDefault();
                setConfirmId(c.combo_id);
              }}
              className="relative shrink-0 cursor-pointer whitespace-nowrap border-0 px-4 transition-colors"
              style={{
                background: 'transparent',
                minWidth: '112px',
                maxWidth: '160px',
                color: isActive
                  ? '#1f6f8b'
                  : c.status === 'abandoned'
                    ? '#b0b8c4'
                    : '#536184',
                fontSize: '13px',
                fontWeight: 700,
                textDecoration: c.status === 'abandoned' ? 'line-through' : 'none',
              }}
              title={`${c.passion} + ${c.strengths.join(', ')}（右键删除）`}
            >
              {isConfirming ? (
                <span className="flex items-center justify-center gap-2 text-[12px]">
                  <span
                    role="button"
                    tabIndex={0}
                    className="text-red-500"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleConfirmDelete(c.combo_id);
                    }}
                  >
                    删除?
                  </span>
                  <span
                    role="button"
                    tabIndex={0}
                    className="text-[#9ca3af]"
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmId(null);
                    }}
                  >
                    取消
                  </span>
                </span>
              ) : (
                <span className="flex items-center justify-center gap-1.5">
                  <span className="text-[11px] opacity-60">
                    {String(idx + 1).padStart(2, '0')}
                  </span>
                  <span className="max-w-[100px] truncate">{c.passion}</span>
                  {c.status === 'concluded' && c.conclusion_card && (
                    <span className="text-[11px]">✓</span>
                  )}
                </span>
              )}
              {!isActive && idx < combos.length - 1 && (
                <span className="absolute right-0 top-3 h-6 w-px bg-[rgba(91,107,159,.10)]" />
              )}
              {isActive && (
                <span
                  className="absolute bottom-0 rounded-t-lg"
                  style={{
                    left: '24%',
                    right: '24%',
                    height: '3px',
                    background: 'linear-gradient(90deg, #67dfda, #70c9ff)',
                    boxShadow: '0 -4px 10px rgba(103,210,238,0.28)',
                  }}
                />
              )}
            </button>
          );
        })}
      </div>

      <button
        type="button"
        disabled={atLimit}
        onClick={enterDraft}
        className="flex shrink-0 items-center gap-1.5 transition-all duration-200 ease-out"
        style={{
          height: '48px',
          padding: '0 16px',
          borderRadius: '14px',
          border: isDraft
            ? '1.2px solid rgba(103,210,238,0.45)'
            : '1.2px solid rgba(255,255,255,0.48)',
          background: atLimit
            ? 'rgba(200,200,220,.2)'
            : isDraft
              ? 'rgba(103,223,218,0.18)'
              : 'rgba(255,255,255,0.55)',
          color: atLimit ? '#b0b8c4' : '#2a7a8c',
          fontSize: '13px',
          fontWeight: 750,
          cursor: atLimit ? 'not-allowed' : 'pointer',
          boxShadow: '0 6px 14px rgba(33,48,79,0.05)',
        }}
        title={atLimit ? `已达上限(${MAX_COMBOS}个)` : '新建组合'}
      >
        <Plus size={18} strokeWidth={2.5} />
        新建组合
      </button>
    </div>
  );
}
