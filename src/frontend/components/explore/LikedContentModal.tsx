'use client';

/**
 * 旅程卡「点赞精选」弹窗：展示某个激活码（旅程）在探索过程中点赞过的内容。
 * 复用 LikedContentSection（强制渲染空态）；报告未解锁的旅程也能查看自己的点赞。
 */

import { useEffect } from 'react';
import { X } from 'lucide-react';
import LikedContentSection from './LikedContentSection';
import { useLocale } from '@/hooks/useLocale';

interface LikedContentModalProps {
  /** 目标旅程的激活码；null 表示关闭 */
  activationCode: string | null;
  onClose: () => void;
}

export default function LikedContentModal({ activationCode, onClose }: LikedContentModalProps) {
  const { t } = useLocale();

  // Esc 关闭
  useEffect(() => {
    if (!activationCode) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [activationCode, onClose]);

  if (!activationCode) return null;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/45 px-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t('dashboard.likedPicks')}
    >
      <div
        className="w-full max-w-2xl max-h-[80vh] overflow-y-auto rounded-2xl bg-bd-bg p-4 shadow-[0_24px_60px_rgba(15,23,42,0.3)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-end">
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close')}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-bd-muted hover:bg-bd-overlay-md hover:text-bd-fg"
          >
            <X size={16} />
          </button>
        </div>
        <LikedContentSection activationCode={activationCode} showEmptyState />
      </div>
    </div>
  );
}
