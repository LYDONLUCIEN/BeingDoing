'use client';

/**
 * v4 最终选择弹窗
 *
 * 从已有 combo 的结论卡中，选择 1–3 个最想继续深入的方向。
 * 每个方向卡片展示 combo 的结论标题、标签、描述。
 */

import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import type { ComboSession, ConclusionCard } from '@/lib/explore/ruminationV4Api';

interface Props {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

const THEMES = [
  { name: 'green', color: '#00a979', tagBg: '#e8faf3', tagColor: '#02a475', icon: '♧' },
  { name: 'purple', color: '#7047ef', tagBg: '#f0ebff', tagColor: '#774cf0', icon: '♙' },
  { name: 'pink', color: '#ef3777', tagBg: '#ffeaf2', tagColor: '#e43a75', icon: '♡' },
  { name: 'yellow', color: '#f3a100', tagBg: '#fff6df', tagColor: '#c98900', icon: 'ϟ' },
  { name: 'blue', color: '#2976ed', tagBg: '#e8f2ff', tagColor: '#2f78e8', icon: '♫' },
  { name: 'orange', color: '#ff8c18', tagBg: '#fff1df', tagColor: '#ed861b', icon: '♧' },
];

function getCardTheme(index: number) {
  return THEMES[index % THEMES.length];
}

/** 防御：dict 形态已废弃，统一转纯字符串 */
function hypToString(h: ConclusionCard['hypothesis']): string {
  if (!h) return '';
  if (typeof h === 'string') return h;
  return Object.values(h).filter(Boolean).join('\n');
}

function getDirectionDesc(combo: ComboSession, card: ConclusionCard | null): string {
  const t = hypToString(card?.hypothesis ?? null).trim();
  if (t) return t;
  return `基于「${combo.passion}」与「${combo.strengths.join('、')}」的探索方向。`;
}

/** 平衡点徽章：绿 ✓ 推荐 / 琥珀 ⚠ 未找到平衡点 / 灰 ？ 未评估（仅提示，不影响可选） */
function BalanceBadge({ card }: { card: ConclusionCard | null }) {
  const found = card?.balance_found ?? null;
  if (found === true) {
    return (
      <span
        className="grid h-[20px] w-[20px] shrink-0 place-items-center rounded-full text-[12px] font-extrabold text-white"
        style={{ background: '#09aa7c' }}
        title="已通过理想与现实的平衡验证"
        aria-label="已通过理想与现实的平衡验证"
      >
        ✓
      </span>
    );
  }
  if (found === false) {
    return (
      <span
        className="grid h-[20px] w-[20px] shrink-0 place-items-center rounded-full text-[12px] font-extrabold text-white"
        style={{ background: '#f0a020' }}
        title={card?.balance_fail_reason?.trim() || '未找到平衡点'}
        aria-label="未找到平衡点"
      >
        ⚠
      </span>
    );
  }
  return (
    <span
      className="grid h-[20px] w-[20px] shrink-0 place-items-center rounded-full text-[12px] font-extrabold text-white"
      style={{ background: '#b6c0cf' }}
      title="AI 尚未完成平衡评估"
      aria-label="AI 尚未完成平衡评估"
    >
      ？
    </span>
  );
}

export default function V4FinalSelectionModal({ open, onClose, onConfirm }: Props) {
  const { state, selectFinal, submitFinal, comboCache } = useRuminationV4Store();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  // 只展示已确认（concluded）且有结论卡的 combo；用户跳过（user_skipped/abandoned）的不进终选
  const candidates = useMemo(() => {
    if (!state) return [];
    return (state.combo_sessions || [])
      .filter((c) => !!c.conclusion_card && c.status === 'concluded' && !c.user_skipped)
      .map((c) => {
        const full = comboCache[c.combo_id] || c;
        return {
          ...c,
          conclusion_card: full.conclusion_card || c.conclusion_card,
        };
      });
  }, [state, comboCache]);

  // 打开时同步后端已选
  useEffect(() => {
    if (open && state?.final_selection?.selected_combo_ids) {
      setSelectedIds(new Set(state.final_selection.selected_combo_ids));
    }
  }, [open, state?.final_selection?.selected_combo_ids]);

  // ESC 关闭
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const toggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 3) {
        next.add(id);
      } else {
        showToast('最多选择 3 个方向');
      }
      return next;
    });
  };

  const count = selectedIds.size;
  const canConfirm = count >= 1 && count <= 3;

  const handleConfirm = async () => {
    if (!canConfirm) return;
    setSubmitting(true);
    try {
      await selectFinal(Array.from(selectedIds));
      await submitFinal();
      onConfirm();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="modal-overlay fixed inset-0 z-[100] flex items-center justify-center p-6"
          style={{ background: 'rgba(17,29,51,0.46)', backdropFilter: 'blur(5px)' }}
          onClick={onClose}
        >
          <motion.section
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.24, ease: 'easeOut' }}
            className="modal relative flex max-h-[92vh] w-[min(820px,82vw)] flex-col overflow-hidden rounded-[20px] p-7"
            style={{
              background: 'rgba(255,255,255,0.97)',
              boxShadow: '0 28px 75px rgba(7,21,50,0.28)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* 装饰光斑 */}
            <span
              className="pointer-events-none absolute rounded-full blur-[20px] opacity-[0.34]"
              style={{
                width: 220,
                height: 150,
                left: -65,
                top: -45,
                background: 'radial-gradient(circle,#88c5ff,transparent 68%)',
              }}
            />
            <span
              className="pointer-events-none absolute rounded-full blur-[20px] opacity-[0.34]"
              style={{
                width: 220,
                height: 150,
                right: -60,
                top: -55,
                background: 'radial-gradient(circle,#ffb47d,transparent 68%)',
              }}
            />

            <button
              type="button"
              onClick={onClose}
              className="modal-close absolute right-4 top-4 z-10 grid h-10 w-10 place-items-center rounded-full border text-2xl transition-colors hover:bg-white"
              style={{
                background: 'rgba(255,255,255,0.85)',
                borderColor: '#dfe5ed',
                color: '#334667',
                boxShadow: '0 4px 12px rgba(13,31,65,0.08)',
              }}
              aria-label="关闭"
            >
              <X size={20} />
            </button>

            <header className="modal-header relative z-[1] text-center">
              <h2 className="m-0 text-2xl font-extrabold tracking-wide text-[#07163b]">
                最终选择 1–3 个方向
              </h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-[#61708b]">
                从已创建的组合中，选择你最想继续深入探索的方向
              </p>
              <span
                className="selected-pill mt-3 inline-flex h-[30px] items-center rounded-full px-4 text-[13px] font-extrabold"
                style={{
                  background: 'linear-gradient(90deg,#e6fbf8,#e5ecff)',
                  color: '#168cc8',
                }}
              >
                已选 {count} / 3
              </span>
            </header>

            <div
              className="direction-grid relative z-[1] mt-5 grid gap-4 overflow-y-auto pr-1"
              style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}
            >
              {candidates.map((combo, idx) => {
                const card = combo.conclusion_card;
                const selected = selectedIds.has(combo.combo_id);
                const theme = getCardTheme(idx);
                const desc = getDirectionDesc(combo, card);
                // 与管理组合口径一致：标题=热爱选项，tag=优势
                const tags = combo.strengths.slice(0, 4);
                return (
                  <button
                    key={combo.combo_id}
                    type="button"
                    onClick={() => toggle(combo.combo_id)}
                    title={desc} // 悬停任意位置可见完整假设（推荐/不推荐均生效）
                    className={`
                      direction-card relative flex flex-col rounded-[15px] border p-4 text-center transition-all duration-200
                      ${selected ? 'selected' : ''}
                    `}
                    style={{
                      minHeight: 140,
                      background: 'rgba(255,255,255,0.8)',
                      borderColor: selected ? theme.color : '#e0e6ee',
                      borderWidth: selected ? '2px' : '1px',
                      padding: selected ? '15px' : '16px',
                      boxShadow: selected
                        ? `0 8px 20px ${theme.color}20`
                        : 'none',
                      color: selected ? theme.color : '#07163b',
                    }}
                  >
                    <span
                      className="direction-index absolute left-2.5 top-2.5 grid h-8 min-w-[32px] place-items-center rounded-full px-1.5 text-[13px] font-extrabold text-white"
                      style={{
                        background: theme.color,
                        boxShadow: `0 5px 10px ${theme.color}36`,
                      }}
                    >
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    {/* 圆角矩形勾选框，与圆形推荐/不推荐徽章区分 */}
                    <span
                      className="direction-check absolute right-2.5 top-2.5 grid h-[22px] w-[22px] place-items-center rounded-[6px] text-white"
                      style={{
                        background: '#09aa7c',
                        display: selected ? 'grid' : 'none',
                        border: '2px solid white',
                      }}
                    >
                      ✓
                    </span>
                    <div className="mx-auto mb-2 mt-4 flex items-start justify-center gap-1.5">
                      <h3
                        className="line-clamp-2 text-base font-bold leading-snug"
                        style={{ color: selected ? theme.color : '#07163b' }}
                      >
                        {combo.passion}
                      </h3>
                      <BalanceBadge card={card} />
                    </div>
                    <div className="tags mb-2 flex flex-wrap justify-center gap-1">
                      {tags.map((t) => (
                        <span
                          key={t}
                          className="tag rounded-md px-1.5 py-1 text-[11px]"
                          style={{
                            background: selected ? theme.tagBg : '#eef3fb',
                            color: selected ? theme.tagColor : '#65728c',
                          }}
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                    {/* 不推荐（未找到平衡点）时直接展示理由 */}
                    {card?.balance_found === false && (
                      <p
                        className="mt-1.5 line-clamp-2 rounded-md px-1.5 py-1 text-left text-[11px] leading-snug"
                        style={{
                          background: '#fff6e5',
                          color: '#b57908',
                        }}
                        title={card.balance_fail_reason?.trim() || '未找到平衡点'}
                      >
                        ⚠ 不推荐：{card.balance_fail_reason?.trim() || '未找到平衡点'}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>

            {candidates.length === 0 && (
              <div className="relative z-[1] my-8 text-center text-sm text-[#9ca3af]">
                还没有已确认结论的组合，
                <br />
                请先在右侧与 AI 探讨并生成结论卡
              </div>
            )}

            <div
              className="modal-note relative z-[1] mx-[-4px] my-4 flex items-center gap-2.5 text-xs text-[#69758d]"
              style={{ color: '#69758d' }}
            >
              <span className="h-px flex-1 bg-[#dce2eb]" />
              <span
                className="info-dot grid h-[17px] w-[17px] place-items-center rounded-full border text-[11px] font-extrabold"
                style={{ borderColor: '#8190a9' }}
              >
                i
              </span>
              <span>你可以稍后继续调整组合</span>
              <span className="h-px flex-1 bg-[#dce2eb]" />
            </div>

            <div className="modal-actions relative z-[1] grid grid-cols-[1fr_1.45fr] gap-5">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="back-btn h-12 rounded-full border bg-white text-[15px] font-extrabold text-[#485671] transition-colors hover:bg-[#f6f8fb] disabled:opacity-50"
                style={{ borderColor: '#d9e0e9' }}
              >
                返回调整
              </button>
              <button
                type="button"
                disabled={!canConfirm || submitting}
                onClick={handleConfirm}
                className="confirm-btn h-12 rounded-full border-0 text-[15px] font-extrabold text-white transition-all disabled:cursor-not-allowed disabled:opacity-45"
                style={{
                  background: canConfirm
                    ? 'linear-gradient(90deg,#3370ff,#277cfa 45%,#17c49b)'
                    : 'rgba(200,200,220,0.5)',
                  boxShadow: canConfirm ? '0 9px 20px rgba(41,113,236,0.18)' : 'none',
                }}
              >
                {submitting ? '保存中…' : `确认选择（${count}/3）`}
              </button>
            </div>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
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
