'use client';

/**
 * 旧浏览器内核提示弹窗（ADR-0020，2026-09-06）。
 *
 * 挂载在首页与探索各 phase 页（values → rumination 共用 chat 页组件），
 * 检测到旧内核（dvh/color-mix 特性缺失）时弹窗推荐 Edge/Chrome。
 * 「我知道了」仅关闭本次（下一个入口页仍会提示）；「不再提示」写
 * localStorage 持久化（浏览器维度）。用户不切换则由 vh 回退/静态色
 * 兜底保证基本可用。z-[250] 盖过 V4IntroModal（z-[230]）等页面弹层。
 *
 * 性能（2026-09-21）：framer-motion 体积大且仅旧内核浏览器才需要，
 * 弹窗本体拆到 LegacyBrowserNoticeDialog 并走 next/dynamic 按需加载，
 * 现代浏览器首屏 bundle 不再包含 framer-motion。
 */

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { shouldShowLegacyNotice, dismissLegacyNotice } from '@/lib/utils/browserCompat';

const LegacyBrowserNoticeDialog = dynamic(() => import('./LegacyBrowserNoticeDialog'), {
  ssr: false,
});

export default function LegacyBrowserNotice() {
  const [open, setOpen] = useState(false);
  // 只有真的弹过窗才挂载动态组件（挂载后保留，供关闭退出动画使用）
  const [everOpened, setEverOpened] = useState(false);

  useEffect(() => {
    if (shouldShowLegacyNotice()) {
      setOpen(true);
      setEverOpened(true);
    }
  }, []);

  const handleDismissForever = () => {
    dismissLegacyNotice();
    setOpen(false);
  };

  if (!everOpened) return null;

  return (
    <LegacyBrowserNoticeDialog
      open={open}
      onClose={() => setOpen(false)}
      onDismissForever={handleDismissForever}
    />
  );
}
