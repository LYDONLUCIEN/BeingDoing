'use client';

import { motion, AnimatePresence } from 'framer-motion';

export type AbuseFrozenModalProps = {
  open: boolean;
  /** 标题，由父组件用 t() 注入 */
  title: string;
  /** 正文（优先用后端 message，父组件兜底 i18n 文案） */
  body: string;
  /** 联系按钮文案（如「联系管理员：openlife.lab@outlook.com」） */
  contactLabel: string;
  /** mailto 目标邮箱 */
  contactEmail: string;
  /** 关闭按钮文案 */
  okLabel: string;
  /** 关闭（不解除冻结，输入区保持禁用） */
  onClose: () => void;
};

/**
 * 滥用冻结弹层（403 abuse_frozen）：风格与 TrialLimitModal 一致的暖色居中弹层，
 * 但无升级/购买引导，仅提供联系管理员入口。
 */
export default function AbuseFrozenModal({
  open,
  title,
  body,
  contactLabel,
  contactEmail,
  okLabel,
  onClose,
}: AbuseFrozenModalProps) {
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
            aria-labelledby="abuse-frozen-title"
            className="relative w-full max-w-md rounded-2xl border border-stone-200/80 bg-white/95 px-8 py-9 shadow-[0_24px_80px_-24px_rgba(15,23,42,0.18),0_0_0_1px_rgba(255,255,255,0.6)_inset]"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5 flex items-center gap-3">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600 ring-1 ring-red-100/80"
                aria-hidden
              >
                {/* 盾牌图标：账号功能冻结 */}
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M9.5 12l2 2 3.5-4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div>
                <h2 id="abuse-frozen-title" className="text-lg font-semibold tracking-tight text-stone-800">
                  {title}
                </h2>
              </div>
            </div>
            <p className="mb-6 whitespace-pre-line text-[15px] leading-relaxed text-stone-600">{body}</p>
            <div className="space-y-3">
              <a
                href={`mailto:${contactEmail}`}
                className="block w-full rounded-xl bg-stone-900 py-3.5 text-center text-sm font-medium text-white shadow-sm transition hover:bg-stone-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400/80 focus-visible:ring-offset-2"
              >
                {contactLabel}
              </a>
              <button
                type="button"
                onClick={onClose}
                className="w-full rounded-xl border border-stone-200 py-3 text-sm font-medium text-stone-500 transition hover:bg-stone-50 hover:text-stone-700"
              >
                {okLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
