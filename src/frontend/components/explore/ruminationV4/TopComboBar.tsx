'use client';

/**
 * v4 组合 tab 条
 *
 * - 胶囊式 tab，带序号 01/02/03，标签截断
 * - hover 显示删除按钮，点击二次确认
 * - 「管理组合」模式：多选 tab，批量删除
 * - 至少保留一个组合
 */

import { useRef, useState, useCallback, useMemo, useEffect, type WheelEvent } from 'react';
import { ChevronLeft, ChevronRight, Plus, Trash2, X } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';

const MAX_COMBOS = 10;

export interface TopComboBarProps {
  /** 管理态变化时通知父级（用于调整外层布局/遮罩） */
  onManageChange?: (managing: boolean) => void;
}

export default function TopComboBar({ onManageChange }: TopComboBarProps) {
  const { state, switchCombo, removeCombo } = useRuminationV4Store();
  const [managing, setManaging] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmSingleId, setConfirmSingleId] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  /** 左右换页按钮是否可用（仅在对应方向可滚动时显示） */
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const combos = useMemo(() => state?.combo_sessions || [], [state]);
  const activeId = state?.active_combo_id ?? null;
  const atLimit = combos.length >= MAX_COMBOS;
  /** 终选已提交：整页回看模式，新建/管理/删除全部禁用，入选 tab 加轻量标记 */
  const finalSubmitted = !!state?.final_selection?.submitted;
  const finalSelectedIds = useMemo(
    () => new Set(state?.final_selection?.selected_combo_ids || []),
    [state?.final_selection?.selected_combo_ids]
  );

  const toggleManaging = useCallback(
    (next: boolean) => {
      setManaging(next);
      setSelectedIds(new Set());
      setConfirmSingleId(null);
      onManageChange?.(next);
    },
    [onManageChange]
  );

  /** 同步左右可滚动状态（hooks 须在 `if (!state) return null` 之前） */
  const updateScrollState = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 1);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    updateScrollState();
    const el = scrollerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(updateScrollState);
    ro.observe(el);
    return () => ro.disconnect();
  }, [combos.length, updateScrollState]);

  if (!state) return null;

  const handleSingleDelete = async (comboId: string) => {
    if (combos.length <= 1) {
      showToast('至少保留一个组合');
      return;
    }
    await removeCombo(comboId);
    setConfirmSingleId(null);
  };

  const handleBatchDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    const remaining = combos.length - ids.length;
    if (remaining < 1) {
      showToast('至少保留一个组合');
      return;
    }
    for (const id of ids) {
      await removeCombo(id);
    }
    setSelectedIds(new Set());
    setManaging(false);
    onManageChange?.(false);
  };

  const toggleSelect = (comboId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(comboId)) next.delete(comboId);
      else next.add(comboId);
      return next;
    });
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

  /** 换页按钮：每次固定滚动约 2 个 tab 的距离 */
  const scrollByFixed = (dir: 1 | -1) => {
    scrollerRef.current?.scrollBy({ left: dir * 480, behavior: 'smooth' });
  };

  const allSelected = combos.length > 0 && combos.every((c) => selectedIds.has(c.combo_id));

  return (
    <div
      className="combo-toolbar flex min-h-[52px] min-w-0 items-center gap-3 rounded-[18px] px-5 py-1.5"
      style={{
        background: 'rgba(255,255,255,0.38)',
        border: '1px solid rgba(255,255,255,0.42)',
        boxShadow: '0 10px 30px rgba(0,0,0,0.03)',
        backdropFilter: 'blur(14px)',
      }}
    >
      <div className="tabs-wrap group/tabs relative flex min-w-0 flex-1 items-center">
        {/* hover 出现的左右换页按钮（仅在对应方向可滚动时渲染） */}
        {canScrollLeft && (
          <button
            type="button"
            aria-label="向左翻页"
            title="向左翻页"
            onClick={() => scrollByFixed(-1)}
            className="absolute -left-2 z-10 flex h-7 w-7 items-center justify-center rounded-full border border-[#e1e6ef] bg-white/95 text-[#45536f] opacity-0 shadow-[0_4px_12px_rgba(19,38,76,0.14)] transition-opacity duration-200 hover:bg-white group-hover/tabs:opacity-100"
          >
            <ChevronLeft size={15} strokeWidth={2.5} />
          </button>
        )}
        <div
          ref={scrollerRef}
          onWheel={onWheel}
          onScroll={updateScrollState}
          className="tabs flex min-w-0 flex-1 items-center gap-3 overflow-x-auto overflow-y-hidden"
          style={{
            scrollbarWidth: 'none',
            WebkitOverflowScrolling: 'touch',
          }}
        >
        {combos.length === 0 && (
          <div className="flex shrink-0 items-center px-2 text-[12px] text-[#9ca3af]">
            还没有组合，选完后点「开始探索」
          </div>
        )}
        {combos.map((c, idx) => {
          const isActive = c.combo_id === activeId && !managing;
          const isSelected = selectedIds.has(c.combo_id);
          const isConfirming = confirmSingleId === c.combo_id;
          /** 提交后入选组合的轻量「被选中」感：紫色描边环，不动布局 */
          const isFinalSelected = finalSubmitted && finalSelectedIds.has(c.combo_id);
          return (
            <button
              key={c.combo_id}
              type="button"
              onClick={() => {
                if (managing) {
                  toggleSelect(c.combo_id);
                  return;
                }
                if (isConfirming) return;
                setConfirmSingleId(null);
                switchCombo(c.combo_id);
              }}
              className={`
                combo-tab group relative flex h-9 shrink-0 cursor-pointer items-center gap-2.5
                overflow-hidden whitespace-nowrap rounded-full border px-4 pr-9 text-left
                transition-all duration-200 ease
                ${isActive ? 'active' : ''}
                ${isSelected ? 'selected' : ''}
                ${managing ? 'managing' : ''}
              `}
              style={{
                width: '232px',
                fontSize: '14px',
                fontWeight: 650,
                color: isActive ? '#078bd8' : isSelected ? '#ef5163' : '#45536f',
                background: isActive
                  ? 'rgba(255,255,255,0.92)'
                  : isSelected
                    ? 'rgba(255,240,240,0.85)'
                    : 'rgba(255,255,255,0.55)',
                borderColor: isFinalSelected
                  ? '#8b7bf5'
                  : isActive
                    ? '#e1e6ef'
                    : isSelected
                      ? '#ffccd0'
                      : '#e1e6ef',
                boxShadow: isFinalSelected
                  ? '0 0 0 1.5px rgba(122,100,255,0.55), 0 4px 15px rgba(19,38,76,0.06)'
                  : '0 4px 15px rgba(19,38,76,0.06)',
              }}
              title={
                managing
                  ? '点击选择/取消选择'
                  : `${c.passion} + ${c.strengths.join('、')}${isFinalSelected ? '（已入选）' : ''}`
              }
            >
              {managing && (
                <span
                  className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px]"
                  style={{
                    borderColor: isSelected ? '#ff416c' : '#c7cdd8',
                    background: isSelected ? '#ff416c' : 'transparent',
                    color: isSelected ? '#fff' : '#9ca3af',
                  }}
                >
                  {isSelected ? '✓' : ''}
                </span>
              )}
              <span
                className="tab-index shrink-0 text-[12px] font-bold"
                style={{ opacity: isActive ? 0.9 : 0.6 }}
              >
                {String(idx + 1).padStart(2, '0')}
              </span>
              <span className="tab-label flex-1 truncate">{`${c.passion} × ${c.strengths.join('、')}`}</span>

              {/* hover 删除按钮（提交后回看模式不渲染） */}
              {!managing && !finalSubmitted && (
                <span
                  role="button"
                  tabIndex={0}
                  className="tab-close absolute right-2 top-1/2 hidden h-5 w-5 -translate-y-1/2 place-items-center rounded-full text-[16px] transition-colors hover:bg-[#fff0f0] hover:text-[#ed5163] group-hover:grid"
                  style={{ color: '#2e4268' }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (combos.length <= 1) {
                      showToast('至少保留一个组合');
                      return;
                    }
                    setConfirmSingleId(c.combo_id);
                  }}
                  title="删除组合"
                >
                  ×
                </span>
              )}

              {isConfirming && (
                <span
                  className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1 text-[11px]"
                  onClick={(e) => e.stopPropagation()}
                >
                  <span
                    role="button"
                    tabIndex={0}
                    className="rounded-full bg-[#fff0f0] px-1.5 py-0.5 text-red-500 hover:bg-[#ffe0e0]"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleSingleDelete(c.combo_id);
                    }}
                  >
                    删除?
                  </span>
                  <span
                    role="button"
                    tabIndex={0}
                    className="rounded-full bg-white/80 px-1.5 py-0.5 text-[#9ca3af] hover:bg-white"
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmSingleId(null);
                    }}
                  >
                    取消
                  </span>
                </span>
              )}

              {isActive && !managing && (
                <span
                  className="absolute bottom-[-3px] left-3 right-3 h-[3px] rounded-full"
                  style={{
                    background: 'linear-gradient(90deg,#17cbd1,#5f8dff)',
                  }}
                />
              )}
            </button>
          );
        })}
        </div>
        {canScrollRight && (
          <button
            type="button"
            aria-label="向右翻页"
            title="向右翻页"
            onClick={() => scrollByFixed(1)}
            className="absolute -right-2 z-10 flex h-7 w-7 items-center justify-center rounded-full border border-[#e1e6ef] bg-white/95 text-[#45536f] opacity-0 shadow-[0_4px_12px_rgba(19,38,76,0.14)] transition-opacity duration-200 hover:bg-white group-hover/tabs:opacity-100"
          >
            <ChevronRight size={15} strokeWidth={2.5} />
          </button>
        )}
      </div>

      {/* 操作按钮区 */}
      <div
        className="toolbar-actions flex shrink-0 items-center gap-3 pl-3"
        style={{ borderLeft: '1px solid #edf0f5' }}
      >
        {managing ? (
          <>
            <button
              type="button"
              onClick={() => toggleManaging(false)}
              className="ghost-btn flex h-9 items-center gap-2 rounded-full border border-[#d9e0e9] bg-white px-3.5 text-[12px] font-semibold text-[#485671] transition-colors hover:bg-[#f6f8fb]"
            >
              <X size={15} />
              取消
            </button>
            <button
              type="button"
              disabled={selectedIds.size === 0}
              onClick={handleBatchDelete}
              className="flex h-9 items-center gap-2 rounded-full border-0 px-3.5 text-[12px] font-semibold text-white transition-all disabled:cursor-not-allowed disabled:opacity-45"
              style={{
                background:
                  selectedIds.size > 0
                    ? 'linear-gradient(135deg,#ff416c,#ff6b36)'
                    : 'rgba(200,200,220,0.5)',
                boxShadow:
                  selectedIds.size > 0 ? '0 8px 18px rgba(255,65,108,0.18)' : 'none',
              }}
            >
              <Trash2 size={15} />
              删除选中（{selectedIds.size}）
            </button>
            {combos.length > 1 && (
              <button
                type="button"
                onClick={() => {
                  if (allSelected) {
                    setSelectedIds(new Set());
                  } else {
                    setSelectedIds(new Set(combos.map((c) => c.combo_id)));
                  }
                }}
                className="text-[12px] font-semibold text-[#485671] underline-offset-2 hover:underline"
              >
                {allSelected ? '取消全选' : '全选'}
              </button>
            )}
          </>
        ) : (
          <>
            {!finalSubmitted && (
              <button
                type="button"
                onClick={() => toggleManaging(true)}
                className="ghost-btn flex h-9 items-center gap-2 rounded-full px-3.5 text-[12px] font-semibold text-[#485671] transition-colors hover:bg-[#f6f8fb]"
              >
                <span>♜</span>
                <span>管理组合</span>
              </button>
            )}
            <button
              type="button"
              disabled={atLimit || finalSubmitted}
              onClick={enterDraft}
              className="new-btn flex h-9 items-center gap-2 rounded-full border bg-white px-3.5 text-[12px] font-semibold transition-all disabled:opacity-50"
              style={{
                borderColor: '#e7eaf0',
                color: atLimit || finalSubmitted ? '#b0b8c4' : '#008ea7',
                boxShadow: '0 6px 16px rgba(21,47,88,0.06)',
                cursor: atLimit || finalSubmitted ? 'not-allowed' : 'pointer',
              }}
              title={
                finalSubmitted
                  ? '最终选择已提交，组合已锁定'
                  : atLimit
                    ? `已达上限(${MAX_COMBOS}个)`
                    : '新建组合'
              }
            >
              <Plus size={16} strokeWidth={2.5} />
              新建组合
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function showToast(text: string) {
  const existing = document.getElementById('rumination-v4-toast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.id = 'rumination-v4-toast';
  toast.className =
    'fixed left-1/2 bottom-8 z-[200] -translate-x-1/2 rounded-full bg-[#0e2045] px-5 py-2.5 text-sm font-medium text-white shadow-lg transition-all duration-200';
  toast.style.opacity = '0';
  toast.style.transform = 'translate(-50%, 20px)';
  toast.textContent = text;
  document.body.appendChild(toast);
  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translate(-50%, 0)';
  });
  window.setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translate(-50%, 20px)';
    window.setTimeout(() => toast.remove(), 200);
  }, 1800);
}
