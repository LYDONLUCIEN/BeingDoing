'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Gift, Loader2 } from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import { claimFreeRenewal } from '@/lib/api/activation';
import { formatLocalDateTime } from '@/lib/utils/formatTime';
import { useLocale } from '@/hooks/useLocale';

export type FreeRenewalClaimModalProps = {
  open: boolean;
  /** 待领取的激活码 */
  code: string | null;
  onClose: () => void;
  /** 领取成功回调（父组件刷新列表） */
  onClaimed?: () => void;
};

/**
 * 7 天免费续期领取弹窗（ADR-0015）。
 * 触发入口：过期通知邮件/站内信链接（/dashboard/codes?free_renewal=<code>）
 * 或「我的激活码」页过期码卡片上的领取按钮。
 */
export default function FreeRenewalClaimModal({
  open,
  code,
  onClose,
  onClaimed,
}: FreeRenewalClaimModalProps) {
  const { t } = useLocale();

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newExpiresAt, setNewExpiresAt] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setSubmitting(false);
    setError(null);
    setNewExpiresAt(null);
  }, [open, code]);

  const handleConfirm = async () => {
    if (!code || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await claimFreeRenewal(code);
      setNewExpiresAt(res.new_expires_at ?? null);
    } catch (e: unknown) {
      setError(getApiErrorMessage(e, t('payment.freeRenewal.failed')));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDone = () => {
    if (newExpiresAt) onClaimed?.();
    onClose();
  };

  const formattedExpiry = newExpiresAt ? formatLocalDateTime(newExpiresAt) : null;

  return (
    <AnimatePresence>
      {open && code ? (
        <motion.div
          className="fixed inset-0 z-[230] flex items-center justify-center px-5"
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
            aria-labelledby="free-renewal-title"
            className="relative w-full max-w-md rounded-2xl border border-stone-200/80 bg-white/95 px-8 py-9 shadow-[0_24px_80px_-24px_rgba(15,23,42,0.18),0_0_0_1px_rgba(255,255,255,0.6)_inset]"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            {newExpiresAt ? (
              /* 领取成功态 */
              <div className="flex flex-col items-center space-y-5 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
                  <Check className="h-6 w-6 text-emerald-600" strokeWidth={2.5} />
                </div>
                <h2 className="text-lg font-semibold tracking-tight text-stone-800">
                  {t('payment.freeRenewal.successTitle')}
                </h2>
                <p className="text-sm leading-relaxed text-stone-600">
                  {t('payment.freeRenewal.successBody', {
                    date: formattedExpiry ?? newExpiresAt,
                  })}
                </p>
                <button
                  type="button"
                  onClick={handleDone}
                  className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white transition hover:bg-stone-800"
                >
                  {t('payment.freeRenewal.done')}
                </button>
              </div>
            ) : (
              <>
                <div className="mb-5 flex items-center gap-3">
                  <div
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100/80"
                    aria-hidden
                  >
                    <Gift className="h-5 w-5" />
                  </div>
                  <h2
                    id="free-renewal-title"
                    className="text-lg font-semibold tracking-tight text-stone-800"
                  >
                    {t('payment.freeRenewal.title')}
                  </h2>
                </div>
                <p className="mb-2 font-mono text-base font-semibold tracking-widest text-stone-900">
                  {code}
                </p>
                <p className="mb-6 whitespace-pre-line text-[15px] leading-relaxed text-stone-600">
                  {t('payment.freeRenewal.body')}
                </p>

                {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

                <div className="space-y-3">
                  <button
                    type="button"
                    onClick={() => void handleConfirm()}
                    disabled={submitting}
                    className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-stone-800 disabled:opacity-40"
                  >
                    {submitting ? (
                      <span className="inline-flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {t('payment.freeRenewal.claiming')}
                      </span>
                    ) : (
                      t('payment.freeRenewal.confirm')
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={onClose}
                    className="w-full rounded-xl border border-stone-200 py-3 text-sm font-medium text-stone-500 transition hover:bg-stone-50 hover:text-stone-700"
                  >
                    {t('payment.freeRenewal.later')}
                  </button>
                </div>
              </>
            )}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
