'use client';

import { motion, AnimatePresence } from 'framer-motion';

export type PhaseCompleteWarmModalProps = {
  open: boolean;
  title: string;
  /** 纯展示文案，由父组件用 t() 注入，与动效/结构解耦 */
  body: string;
  continueLabel: string;
  onContinue: () => void;
};

/**
 * 阶段完成祝贺弹层：结构固定，文案全部由父组件传入。
 */
export default function PhaseCompleteWarmModal({
  open,
  title,
  body,
  continueLabel,
  onContinue,
}: PhaseCompleteWarmModalProps) {
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
            onClick={onContinue}
          />
          <motion.div
            role="dialog"
            aria-modal
            aria-labelledby="phase-complete-title"
            className="relative w-full max-w-md rounded-2xl border border-stone-200/80 bg-white/95 px-8 py-9 shadow-[0_24px_80px_-24px_rgba(15,23,42,0.18),0_0_0_1px_rgba(255,255,255,0.6)_inset]"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5 flex items-center gap-3">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100/80"
                aria-hidden
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <h2 id="phase-complete-title" className="text-lg font-semibold tracking-tight text-stone-800">
                  {title}
                </h2>
              </div>
            </div>
            <p className="mb-8 whitespace-pre-line text-[15px] leading-relaxed text-stone-600">{body}</p>
            <button
              type="button"
              onClick={onContinue}
              className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-stone-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/80 focus-visible:ring-offset-2"
            >
              {continueLabel}
            </button>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
