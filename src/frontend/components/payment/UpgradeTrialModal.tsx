'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Loader2 } from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  applyToTrial,
  getUpgradeContext,
  patchPreferences,
  type UpgradeContext,
} from '@/lib/api/activation';
import { useLocale } from '@/hooks/useLocale';

export type UpgradeTrialModalProps = {
  open: boolean;
  /** 关闭（含「暂不升级」）；内部会在勾选时持久化「不再提醒」 */
  onClose: () => void;
  /** 升级成功回调：参数为升级后的试用码（码字符串不变）与被消耗的付费码 */
  onUpgraded?: (trialCode: string, consumedCode?: string) => void;
  /** 优先展示的码（如刚交付的订单码），排在列表前 */
  preferredCodes?: string[];
  /** 是否展示「不再提醒」勾选（支付结果页/购买成功场景；拦截点不传） */
  showDontRemind?: boolean;
};

/**
 * 消耗升级弹窗（ADR-0014）：作废 1 个未绑定激活码，把已开聊的试用码原地升级为完整码。
 * 触发入口：支付结果页 / PurchaseModal 成功视图 / 试用拦截点 / 我的激活码页。
 * 弹层模式与 TrialLimitModal 一致，z-[230] 以盖在 PurchaseModal（z-[210]）之上。
 */
export default function UpgradeTrialModal({
  open,
  onClose,
  onUpgraded,
  preferredCodes,
  showDontRemind = false,
}: UpgradeTrialModalProps) {
  const { t } = useLocale();
  const router = useRouter();

  const [ctx, setCtx] = useState<UpgradeContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  /** 空态（无可用未绑定码）时的手动输入码：覆盖被赠码等系统不可见的场景 */
  const [manualCode, setManualCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [upgradedCode, setUpgradedCode] = useState<string | null>(null);
  /** 本次升级实际消耗的付费码（成功后供父组件从展示列表排除） */
  const [consumedCode, setConsumedCode] = useState<string | null>(null);
  const [dontRemind, setDontRemind] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCtx(null);
    setSelected(null);
    setManualCode('');
    setError(null);
    setUpgradedCode(null);
    setConsumedCode(null);
    setDontRemind(false);
    setLoading(true);
    getUpgradeContext()
      .then((res) => {
        setCtx(res);
        const codes = res.unbound_codes ?? [];
        if (codes.length > 0) {
          const preferred = (preferredCodes ?? []).find((c) =>
            codes.some((it) => it.code === c),
          );
          setSelected(preferred ?? codes[0].code);
        }
      })
      .catch(() => setCtx(null))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleClose = useCallback(() => {
    if (showDontRemind && dontRemind) {
      patchPreferences({ upgrade_modal_dont_remind: true }).catch(() => {
        /* 偏好保存失败静默 */
      });
    }
    onClose();
  }, [showDontRemind, dontRemind, onClose]);

  const handleConfirm = async () => {
    // 列表选择优先；空态时用手动输入的码（后端校验 active/full/未绑定，错误透传）
    const codeToConsume = selected ?? manualCode.trim().toUpperCase();
    if (!codeToConsume || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await applyToTrial(codeToConsume);
      setUpgradedCode(res.trial_code);
      setConsumedCode(codeToConsume);
    } catch (e: unknown) {
      setError(getApiErrorMessage(e, t('payment.upgrade.failed')));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDone = () => {
    if (upgradedCode) onUpgraded?.(upgradedCode, consumedCode ?? undefined);
    onClose();
  };

  // 优先码排前，其余保持后端顺序
  const orderedCodes = (() => {
    const codes = ctx?.unbound_codes ?? [];
    const preferred = preferredCodes ?? [];
    return [...codes].sort((a, b) => {
      const pa = preferred.includes(a.code) ? 0 : 1;
      const pb = preferred.includes(b.code) ? 0 : 1;
      return pa - pb;
    });
  })();

  return (
    <AnimatePresence>
      {open ? (
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
            onClick={handleClose}
          />
          <motion.div
            role="dialog"
            aria-modal
            aria-labelledby="upgrade-trial-title"
            className="relative w-full max-w-md rounded-2xl border border-stone-200/80 bg-white/95 px-8 py-9 shadow-[0_24px_80px_-24px_rgba(15,23,42,0.18),0_0_0_1px_rgba(255,255,255,0.6)_inset]"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            {upgradedCode ? (
              /* 升级成功态 */
              <div className="flex flex-col items-center space-y-5 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
                  <Check className="h-6 w-6 text-emerald-600" strokeWidth={2.5} />
                </div>
                <h2 className="text-lg font-semibold tracking-tight text-stone-800">
                  {t('payment.upgrade.successTitle')}
                </h2>
                <p className="text-sm leading-relaxed text-stone-600">
                  {t('payment.upgrade.successBody')}
                </p>
                <p className="font-mono text-xl font-bold tracking-widest text-stone-900">
                  {upgradedCode}
                </p>
                <button
                  type="button"
                  onClick={handleDone}
                  className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white transition hover:bg-stone-800"
                >
                  {t('payment.upgrade.done')}
                </button>
              </div>
            ) : (
              <>
                <div className="mb-5 flex items-center gap-3">
                  <div
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-600 ring-1 ring-amber-100/80"
                    aria-hidden
                  >
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2l2.4 7.2H22l-6 4.4 2.3 7.4-6.3-4.6-6.3 4.6L8 13.6 2 9.2h7.6z" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                  <h2 id="upgrade-trial-title" className="text-lg font-semibold tracking-tight text-stone-800">
                    {t('payment.upgrade.title')}
                  </h2>
                </div>
                <p className="mb-5 whitespace-pre-line text-[15px] leading-relaxed text-stone-600">
                  {t('payment.upgrade.body')}
                </p>

                {loading ? (
                  <div className="flex justify-center py-6">
                    <Loader2 className="h-6 w-6 animate-spin text-stone-400" />
                  </div>
                ) : orderedCodes.length === 0 ? (
                  /* 空态：无自购未绑定码 → 手动输入（覆盖被赠码等系统不可见的场景） */
                  <div className="mb-5 space-y-2">
                    <p className="rounded-xl border border-stone-200/80 bg-stone-50/80 px-4 py-3 text-sm text-stone-500">
                      {t('payment.upgrade.noCodes')}
                    </p>
                    <input
                      type="text"
                      value={manualCode}
                      onChange={(e) => setManualCode(e.target.value.toUpperCase())}
                      placeholder={t('payment.upgrade.manualPlaceholder')}
                      className="w-full rounded-xl border border-stone-200 bg-white px-4 py-3 font-mono text-sm tracking-widest text-stone-800 placeholder:font-sans placeholder:tracking-normal placeholder:text-stone-400 focus:border-stone-900 focus:outline-none"
                    />
                  </div>
                ) : (
                  <div className="mb-5 space-y-2">
                    <p className="text-xs font-medium text-stone-500">
                      {t('payment.upgrade.selectLabel')}
                    </p>
                    {orderedCodes.map((item) => (
                      <button
                        key={item.code}
                        type="button"
                        onClick={() => setSelected(item.code)}
                        className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition ${
                          selected === item.code
                            ? 'border-stone-900 bg-stone-900/[0.03] ring-1 ring-stone-900/60'
                            : 'border-stone-200 bg-stone-50/60 hover:bg-stone-100/60'
                        }`}
                      >
                        <span className="font-mono text-sm font-semibold tracking-widest text-stone-800">
                          {item.code}
                        </span>
                        <span className="text-xs text-stone-500">
                          {item.package_type === 'annual'
                            ? t('payment.upgrade.packageAnnual')
                            : t('payment.upgrade.packageQuarterly')}
                        </span>
                      </button>
                    ))}
                  </div>
                )}

                {/* 试用码未开聊：建议直接用新码开始，保留仍要升级兼底 */}
                {!loading && ctx && !ctx.has_started_trial && !upgradedCode && (
                  <div className="mb-5 rounded-xl border border-amber-200/70 bg-amber-50/70 px-4 py-3">
                    <p className="text-sm leading-relaxed text-amber-800">
                      {t('payment.upgrade.notStartedNotice')}
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        const code =
                          (preferredCodes ?? [])[0] ?? ctx.unbound_codes?.[0]?.code ?? '';
                        onClose();
                        router.push(
                          code
                            ? `/explore/activate?code=${encodeURIComponent(code)}`
                            : '/explore/activate',
                        );
                      }}
                      className="mt-2 text-sm font-medium text-amber-900 underline underline-offset-2 hover:text-amber-700"
                    >
                      {t('payment.upgrade.notStartedGo')}
                    </button>
                  </div>
                )}

                {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

                {showDontRemind && (
                  <label className="mb-5 flex cursor-pointer items-center gap-2 text-sm text-stone-500">
                    <input
                      type="checkbox"
                      checked={dontRemind}
                      onChange={(e) => setDontRemind(e.target.checked)}
                      className="h-4 w-4 rounded border-neutral-300 accent-stone-700"
                    />
                    {t('payment.upgrade.dontRemind')}
                  </label>
                )}

                <div className="space-y-3">
                  <button
                    type="button"
                    onClick={() => void handleConfirm()}
                    disabled={(!selected && !manualCode.trim()) || submitting}
                    className="w-full rounded-xl bg-stone-900 py-3.5 text-sm font-medium text-white shadow-sm transition hover:bg-stone-800 disabled:opacity-40"
                  >
                    {submitting ? t('payment.upgrade.upgrading') : t('payment.upgrade.confirm')}
                  </button>
                  <button
                    type="button"
                    onClick={handleClose}
                    className="w-full rounded-xl border border-stone-200 py-3 text-sm font-medium text-stone-500 transition hover:bg-stone-50 hover:text-stone-700"
                  >
                    {t('payment.upgrade.later')}
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
