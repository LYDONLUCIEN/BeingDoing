'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { Users } from 'lucide-react';
import { useLocale } from '@/hooks/useLocale';

export type TeamAnalysisNoticeModalProps = {
  open: boolean;
  onClose: () => void;
};

/**
 * 团队分析报告内联提示框（年度套餐 3 码交付后展示）。
 * 供 PurchaseModal 成功视图内嵌使用（PurchaseModal 本身已是弹层，不再叠弹窗）。
 */
export function TeamAnalysisNoticeBox() {
  const { t } = useLocale();
  return (
    <div className="w-full space-y-1.5 rounded-xl border border-sky-200/80 bg-sky-50/60 px-4 py-3.5 text-left">
      <p className="flex items-center gap-1.5 text-xs font-medium text-stone-700">
        <Users className="h-3.5 w-3.5 text-sky-600" />
        {t('payment.success.teamNoticeTitle')}
      </p>
      <p className="text-[11px] leading-relaxed text-stone-500">
        {t('payment.success.teamNoticeBody')}
      </p>
    </div>
  );
}

/**
 * 团队分析报告提示弹窗：年度套餐（3 人团队码）支付成功后弹出，
 * 告知用户通过邮件申请团队分析报告。弹层模式与 FreeRenewalClaimModal 一致，
 * z-[230] 以盖在 PurchaseModal（z-[210]）之上。
 */
export default function TeamAnalysisNoticeModal({ open, onClose }: TeamAnalysisNoticeModalProps) {
  const { t } = useLocale();

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[230] flex items-center justify-center px-5"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="team-analysis-notice-title"
            className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
            initial={{ scale: 0.96, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.96, y: 8 }}
          >
            <div className="mb-5 flex items-center gap-3">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-sky-50 text-sky-600 ring-1 ring-sky-100/80"
                aria-hidden
              >
                <Users className="h-5 w-5" />
              </div>
              <h2
                id="team-analysis-notice-title"
                className="text-lg font-semibold tracking-tight text-stone-800"
              >
                {t('payment.success.teamNoticeTitle')}
              </h2>
            </div>
            <p className="mb-6 whitespace-pre-line text-[15px] leading-relaxed text-stone-600">
              {t('payment.success.teamNoticeBody')}
            </p>
            <button
              type="button"
              onClick={onClose}
              className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-stone-800"
            >
              {t('payment.success.teamNoticeOk')}
            </button>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
