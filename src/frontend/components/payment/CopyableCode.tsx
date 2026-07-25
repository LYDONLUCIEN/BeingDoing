'use client';

import { Check, Copy } from 'lucide-react';

/**
 * 单个可复制码行（自己的码 / 赠品码共用）。
 * 购买弹窗（PurchaseModal）与支付结果页（/payment/result）复用。
 */
export function CopyableCode({
  code,
  copiedCode,
  onCopy,
  t,
}: {
  code: string;
  copiedCode: string | null;
  onCopy: (code: string) => void;
  t: (k: string) => string;
}) {
  const copied = copiedCode === code;
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-stone-200/80 bg-stone-50/60 px-3.5 py-2.5">
      <span className="font-mono text-sm font-semibold tracking-widest text-stone-900">{code}</span>
      <button
        type="button"
        onClick={() => onCopy(code)}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-stone-200 px-2.5 py-1 text-xs font-medium text-stone-600 transition hover:bg-stone-100"
      >
        {copied ? (
          <>
            <Check className="h-3.5 w-3.5 text-emerald-500" />
            {t('payment.copied')}
          </>
        ) : (
          <>
            <Copy className="h-3.5 w-3.5" />
            {t('payment.copy')}
          </>
        )}
      </button>
    </div>
  );
}
