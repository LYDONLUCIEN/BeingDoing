'use client';

import { motion, AnimatePresence } from 'framer-motion';

export type TrialLimitModalProps = {
  open: boolean;
  title: string;
  /** 纯展示文案，由父组件用 t() 注入，与动效/结构解耦 */
  body: string;
  primaryLabel: string;
  secondaryLabel?: string;
  /** 额外操作（ADR-0014：「使用已有激活码升级」），位于主按钮与次按钮之间 */
  extraLabel?: string;
  onExtra?: () => void;
  /** 主按钮：进入购买引导 */
  onPrimary: () => void;
  /** 遮罩 / 次按钮关闭 */
  onClose: () => void;
};

/**
 * 试用拦截购买引导弹层（P-A）：风格与 PhaseCompleteWarmModal 一致的暖色弹层。
 * 触发场景：402 trial_limit_reached（试用 10 轮用完）/ trial_phase_locked（试用码进非价值观阶段）。
 */
export default function TrialLimitModal({
  open,
  title,
  body,
  primaryLabel,
  secondaryLabel,
  extraLabel,
  onExtra,
  onPrimary,
  onClose,
}: TrialLimitModalProps) {
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
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal
            aria-labelledby="trial-limit-title"
            className="relative w-full max-w-md rounded-2xl border border-stone-200/80 bg-white/95 px-8 py-9 shadow-[0_24px_80px_-24px_rgba(15,23,42,0.18),0_0_0_1px_rgba(255,255,255,0.6)_inset]"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5 flex items-center gap-3">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-600 ring-1 ring-amber-100/80"
                aria-hidden
              >
                {/* 钥匙图标：解锁完整版 */}
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="8" cy="15" r="4" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M10.85 12.15L19 4m-3 3 2.5 2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <h2 id="trial-limit-title" className="text-lg font-semibold tracking-tight text-stone-800">
                  {title}
                </h2>
              </div>
            </div>
            <p className="mb-6 whitespace-pre-line text-[15px] leading-relaxed text-stone-600">{body}</p>
            <div className="space-y-3">
              <button
                type="button"
                onClick={onPrimary}
                className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-stone-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/80 focus-visible:ring-offset-2"
              >
                {primaryLabel}
              </button>
              {extraLabel && onExtra ? (
                <button
                  type="button"
                  onClick={onExtra}
                  className="w-full rounded-xl border border-stone-300 py-3 text-sm font-medium text-stone-700 transition hover:bg-stone-50"
                >
                  {extraLabel}
                </button>
              ) : null}
              {secondaryLabel ? (
                <button
                  type="button"
                  onClick={onClose}
                  className="w-full rounded-xl border border-stone-200 py-3 text-sm font-medium text-stone-500 transition hover:bg-stone-50 hover:text-stone-700"
                >
                  {secondaryLabel}
                </button>
              ) : null}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
