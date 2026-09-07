'use client';

/**
 * 旧浏览器内核提示弹窗（ADR-0020，2026-09-06）。
 *
 * 挂载在首页与探索各 phase 页（values → rumination 共用 chat 页组件），
 * 检测到旧内核（dvh/color-mix 特性缺失）时弹窗推荐 Edge/Chrome。
 * 「我知道了」仅关闭本次（下一个入口页仍会提示）；「不再提示」写
 * localStorage 持久化（浏览器维度）。用户不切换则由 vh 回退/静态色
 * 兜底保证基本可用。z-[250] 盖过 V4IntroModal（z-[230]）等页面弹层。
 */

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { MonitorSmartphone } from 'lucide-react';
import { shouldShowLegacyNotice, dismissLegacyNotice } from '@/lib/utils/browserCompat';

export default function LegacyBrowserNotice() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (shouldShowLegacyNotice()) setOpen(true);
  }, []);

  const handleDismissForever = () => {
    dismissLegacyNotice();
    setOpen(false);
  };

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[250] flex items-center justify-center px-5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="legacy-browser-notice-title"
            className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
            initial={{ scale: 0.96, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.96, y: 8 }}
          >
            <div className="mb-4 flex items-center gap-3">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-sky-50 text-sky-600 ring-1 ring-sky-100"
                aria-hidden
              >
                <MonitorSmartphone className="h-5 w-5" />
              </div>
              <h2
                id="legacy-browser-notice-title"
                className="text-lg font-semibold tracking-tight text-stone-800"
              >
                建议更换浏览器
              </h2>
            </div>

            <div className="mb-6 space-y-3 text-[15px] leading-relaxed text-stone-600">
              <p>
                检测到当前浏览器内核版本较旧，页面布局和显示可能会出现异常。
              </p>
              <p>
                推荐使用最新版
                <span className="font-medium text-stone-800"> Microsoft Edge </span>
                或
                <span className="font-medium text-stone-800"> Google Chrome </span>
                浏览器访问，以获得完整、流畅的体验。
              </p>
              <p className="text-[13px] text-stone-400">
                暂不更换也可以继续使用，我们会尽量保证基本功能可用。
              </p>
            </div>

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="flex-1 rounded-xl border border-stone-200 py-3 text-sm font-medium text-stone-600 transition hover:bg-stone-50"
              >
                我知道了
              </button>
              <button
                type="button"
                onClick={handleDismissForever}
                className="flex-1 rounded-xl bg-stone-900 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-stone-800"
              >
                不再提示
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
