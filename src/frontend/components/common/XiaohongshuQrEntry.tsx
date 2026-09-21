'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { QrCode, X } from 'lucide-react';
import { useLocale } from '@/hooks/useLocale';

/**
 * 小红书二维码入口（2026-09-21 起）：小图标按钮 → 点击弹窗显示完整二维码卡片。
 * 使用位置：首页 LandingFooter（「关于我们」左侧）、/about 文字面板右上角。
 * 弹窗经 createPortal 挂到 body：父级 stacking context（如 .ol-footer z-index:5）
 * 会压住 fixed 弹层的 z-index，portal 后 z-index 90 即可盖过 TopNavbar（z-50）。
 */
export default function XiaohongshuQrEntry({ className = '' }: { className?: string }) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className={className}
        title={t('footer.qrCode')}
        aria-label={t('footer.qrCode')}
        onClick={() => setOpen(true)}
      >
        <QrCode size={15} strokeWidth={1.8} />
      </button>
      {mounted &&
        open &&
        createPortal(
          <div
            className="ol-qr-modal-overlay"
            role="dialog"
            aria-modal="true"
            aria-label={t('footer.qrCode')}
            onClick={() => setOpen(false)}
          >
            <div className="ol-qr-modal" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                className="ol-qr-modal-close"
                aria-label={t('common.close')}
                onClick={() => setOpen(false)}
              >
                <X size={18} />
              </button>
              <img
                src="/assets/openlife-journey/xiaohongshu-qr.webp?v=20260921"
                alt={t('footer.qrCode')}
              />
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
