'use client';

import { motion, AnimatePresence } from 'framer-motion';

export type ContinueConfirmModalProps = {
  open: boolean;
  title: string;
  /** 纯展示文案（支持 \n 换行），由父组件用 t() 注入 */
  body: string;
  primaryLabel: string;
  secondaryLabel: string;
  /** 主按钮：确认进入下一步 */
  onPrimary: () => void;
  /** 遮罩 / 次按钮关闭 */
  onClose: () => void;
};

/**
 * 「完成并继续」二次确认弹层（前四阶段 values/strengths/interests/purpose）：
 * 告知用户进入下一阶段后本阶段对话与结论卡将锁定、不可返回修改，
 * 若对本轮对话不确定可点左侧「新建对话」继续挖掘。风格与 TrialLimitModal 一致。
 */
export default function ContinueConfirmModal({
  open,
  title,
  body,
  primaryLabel,
  secondaryLabel,
  onPrimary,
  onClose,
}: ContinueConfirmModalProps) {
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
            aria-labelledby="continue-confirm-title"
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
                {/* 警示图标：确认后不可修改 */}
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path
                    d="M12 9v4m0 4h.01M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0Z"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <div>
                <h2 id="continue-confirm-title" className="text-lg font-semibold tracking-tight text-stone-800">
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
              <button
                type="button"
                onClick={onClose}
                className="w-full rounded-xl border border-stone-200 py-3 text-sm font-medium text-stone-500 transition hover:bg-stone-50 hover:text-stone-700"
              >
                {secondaryLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
