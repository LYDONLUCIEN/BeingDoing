'use client';

import { motion, AnimatePresence } from 'framer-motion';

export type PhaseWelcomeModalProps = {
  open: boolean;
  /** 阶段名，例如「价值观探索」 */
  phaseLabel: string;
  /** 阶段编号，例如 01 */
  phaseNum: string;
  /** 预估时长展示文案，例如「本轮约需 30~45 分钟」 */
  estimateLabel: string;
  /** 进度自动保存提示 */
  autoSaveHint: string;
  /** 安抚提示：可随时离开、按自己节奏来 */
  reassuranceHint: string;
  /** 主按钮文案 */
  startLabel: string;
  /** 关闭回调（关闭即视为已读，由父组件按 激活码+phase 持久化，每个 phase 只显示一次） */
  onClose: () => void;
};

/**
 * 进入新 phase 的时间预估欢迎卡：
 * 告知本轮预计耗时 + 进度自动保存 + 可中途离开，
 * 让用户安心开始、知道可以休息。结构与 PhaseCompleteWarmModal 解耦，
 * z-index 同为 z-[210]，但触发条件天然互斥（仅 !phaseInteractionLocked 时弹）。
 * 每个激活码+phase 只显示一次：首次进入弹出，关闭后父组件自动持久化，之后不再出现。
 */
export default function PhaseWelcomeModal({
  open,
  phaseLabel,
  phaseNum,
  estimateLabel,
  autoSaveHint,
  reassuranceHint,
  startLabel,
  onClose,
}: PhaseWelcomeModalProps) {
  const handleClose = () => {
    onClose();
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[210] flex items-center justify-center px-5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.25, 0.8, 0.35, 1] }}
        >
          <button
            type="button"
            className="absolute inset-0 bg-stone-900/25 backdrop-blur-[2px]"
            aria-label="Close overlay"
            onClick={handleClose}
          />
          <motion.div
            role="dialog"
            aria-modal
            aria-labelledby="phase-welcome-title"
            className="relative w-full max-w-md rounded-2xl border border-stone-200/80 bg-white/95 px-8 py-9 shadow-[0_24px_80px_-24px_rgba(15,23,42,0.18),0_0_0_1px_rgba(255,255,255,0.6)_inset]"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5">
              <p className="mb-1 text-xs font-medium uppercase tracking-[0.2em] text-stone-400">
                {phaseNum}
              </p>
              <h2 id="phase-welcome-title" className="text-lg font-semibold tracking-tight text-stone-800">
                {phaseLabel}
              </h2>
            </div>

            <div className="mb-6 flex items-center gap-3 rounded-xl border border-stone-200/80 bg-stone-50/80 px-4 py-3">
              <div
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100/80"
                aria-hidden
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 7v5l3 2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <p className="text-sm font-medium text-stone-700">{estimateLabel}</p>
            </div>

            <ul className="mb-6 space-y-2.5">
              <li className="flex items-start gap-2.5 text-[13px] leading-relaxed text-stone-600">
                <svg
                  className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden
                >
                  <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{autoSaveHint}</span>
              </li>
              <li className="flex items-start gap-2.5 text-[13px] leading-relaxed text-stone-600">
                <svg
                  className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden
                >
                  <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{reassuranceHint}</span>
              </li>
            </ul>

            <button
              type="button"
              onClick={handleClose}
              className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-stone-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/80 focus-visible:ring-offset-2"
            >
              {startLabel}
            </button>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
