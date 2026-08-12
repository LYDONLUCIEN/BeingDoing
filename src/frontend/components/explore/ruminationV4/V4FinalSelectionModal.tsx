'use client';

/**
 * v4 最终选择弹窗
 *
 * 从已有 combo 的结论卡中，选择 1–3 个最想继续深入的方向。
 * 每个方向卡片展示 combo 的结论标题、标签、描述。
 */

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import V4FinalSelectionCard from './V4FinalSelectionCard';

interface Props {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export default function V4FinalSelectionModal({ open, onClose, onConfirm }: Props) {
  const { state, selectFinal, submitFinal, comboCache, activationCode } = useRuminationV4Store();
  const router = useRouter();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  /** 已最终提交：终选锁定只读，不可再改（后端同时有 locked 断言） */
  const locked = !!state?.final_selection?.submitted;

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
    if (locked) return; // 已锁定：禁止改选
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
    if (locked || !canConfirm) return;
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
                background: 'radial-gradient(circle,#b9a8ff,transparent 68%)',
              }}
            />
            <span
              className="pointer-events-none absolute rounded-full blur-[20px] opacity-[0.34]"
              style={{
                width: 220,
                height: 150,
                right: -60,
                top: -55,
                background: 'radial-gradient(circle,#8f76ff,transparent 68%)',
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
                {locked
                  ? '最终选择已提交并锁定，报告已生成，不可再修改'
                  : '从已创建的组合中，选择你最想继续深入探索的方向'}
              </p>
              <span
                className="selected-pill mt-3 inline-flex h-[30px] items-center rounded-full px-4 text-[13px] font-extrabold"
                style={{
                  background: 'linear-gradient(90deg,#f4f1ff,#ece7ff)',
                  color: '#5d49ef',
                }}
              >
                已选 {count} / 3
              </span>
            </header>

            {/* 2 列大卡网格（设计稿 uidesign/beautiful/nto3.png） */}
            <div
              className="direction-grid relative z-[1] mt-5 grid gap-5 overflow-y-auto pr-1"
              style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}
            >
              {candidates.map((combo, idx) => (
                <V4FinalSelectionCard
                  key={combo.combo_id}
                  index={idx}
                  combo={combo}
                  card={combo.conclusion_card}
                  selected={selectedIds.has(combo.combo_id)}
                  locked={locked}
                  onToggle={toggle}
                />
              ))}
            </div>

            {candidates.length === 0 && (
              <div className="relative z-[1] my-8 text-center text-sm text-[#9ca3af]">
                还没有已确认结论的组合，
                <br />
                请先在右侧与我探讨并生成结论卡
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
              <span>{locked ? '报告已生成，最终选择不可再修改' : '你可以稍后继续调整组合'}</span>
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
                {locked ? '关闭' : '返回调整'}
              </button>
              {locked ? (
                <button
                  type="button"
                  onClick={() => {
                        onClose();
                        router.push(
                          activationCode
                            ? `/explore/report?code=${encodeURIComponent(activationCode)}`
                            : '/explore/report'
                        );
                      }}
                  className="confirm-btn h-12 rounded-full border-0 text-[15px] font-extrabold text-white transition-all"
                  style={{
                    background: 'linear-gradient(90deg,#826aff,#553df2)',
                    boxShadow: '0 9px 20px rgba(91,65,240,0.22)',
                  }}
                >
                  查看报告
                </button>
              ) : (
                <button
                  type="button"
                  disabled={!canConfirm || submitting}
                  onClick={handleConfirm}
                  className="confirm-btn h-12 rounded-full border-0 text-[15px] font-extrabold text-white transition-all disabled:cursor-not-allowed disabled:opacity-45"
                  style={{
                    background: canConfirm
                      ? 'linear-gradient(90deg,#826aff,#553df2)'
                      : 'rgba(200,200,220,0.5)',
                    boxShadow: canConfirm ? '0 9px 20px rgba(91,65,240,0.22)' : 'none',
                  }}
                >
                  {submitting ? '保存中…' : `确认选择（${count}/3）`}
                </button>
              )}
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
