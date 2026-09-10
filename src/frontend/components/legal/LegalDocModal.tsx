'use client';

import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export type LegalDocModalProps = {
  open: boolean;
  title: string;
  body: string;
  onClose: () => void;
};

/**
 * 法律协议展示弹层：纯展示，title/body 由父组件通过 t() 注入。
 * - 点遮罩关闭
 * - ESC 关闭
 * - 正文 whitespace-pre-line 滚动渲染
 * 卡片复用通用毛玻璃质感 .bd-glass-card（与 /explore/intro 的 bd-intro-card 同源）。
 */
export default function LegalDocModal({ open, title, body, onClose }: LegalDocModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    // 打开时锁定背景滚动
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

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
            aria-label="关闭"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal
            aria-labelledby="legal-doc-title"
            className="bd-glass-card relative w-full max-w-2xl max-h-[80vh] flex flex-col rounded-2xl"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* 标题栏 + 关闭按钮 */}
            <div className="flex items-center justify-between gap-4 px-7 py-5 border-b border-bd-border">
              <h2 id="legal-doc-title" className="text-lg font-semibold tracking-tight text-bd-fg">
                {title}
              </h2>
              <button
                type="button"
                onClick={onClose}
                aria-label="关闭"
                className="shrink-0 rounded-full p-1.5 text-bd-subtle hover:bg-bd-overlay hover:text-bd-fg transition focus:outline-none focus-visible:ring-2 focus-visible:ring-bd-primary/60"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
            {/* 正文（滚动） */}
            <div className="overflow-y-auto px-7 py-6">
              <p className="whitespace-pre-line text-[14px] leading-[1.75] text-bd-muted">{body}</p>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
