'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import type { AxiosError } from 'axios';
import { Check, Copy, Loader2, XCircle } from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import { getOrderByNo, type OrderItem } from '@/lib/api/payment';
import { getUpgradeContext } from '@/lib/api/activation';
import { useLocale } from '@/hooks/useLocale';
import { CopyableCode } from '@/components/payment/CopyableCode';
import UpgradeTrialModal from '@/components/payment/UpgradeTrialModal';

const POLL_INTERVAL_MS = 2000;
const CONFIRM_TIMEOUT_MS = 30 * 60 * 1000;

type ViewState = 'loading' | 'confirming' | 'granted' | 'closed' | 'invalid' | 'error';

/** 判断是否为登录态失效（401/403）：需停止轮询并提示重新登录，避免永远卡在「确认中」 */
function isAuthError(e: unknown): boolean {
  const status = (e as AxiosError)?.response?.status;
  return status === 401 || status === 403;
}

/**
 * 支付结果页：支付宝收银台（page.pay）同步回跳地址。
 * URL 带 out_trade_no（订单号），按订单号查询并每 2s 轮询，
 * 直到 granted / closed / cancelled / refunded，或 30 分钟超时。
 */
function PaymentResultContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { t } = useLocale();

  const outTradeNo = searchParams.get('out_trade_no') || '';

  const [view, setView] = useState<ViewState>(outTradeNo ? 'loading' : 'invalid');
  const [order, setOrder] = useState<OrderItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  /** 消耗升级弹窗（ADR-0014）：套餐交付且有已开聊试用码时弹出 */
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [trialUpgraded, setTrialUpgraded] = useState(false);
  /** 弹窗消耗升级实际用掉的付费码（从展示列表排除，避免把已消耗码当可转赠码展示） */
  const [consumedCode, setConsumedCode] = useState<string | null>(null);
  const upgradeCheckedRef = useRef(false);

  const deadlineRef = useRef<number>(0);

  const applyOrder = useCallback((ord: OrderItem): boolean => {
    /** 返回是否已到达终态 */
    setOrder(ord);
    if (ord.status === 'granted') {
      setView('granted');
      if (ord.meta?.auto_upgraded) setTrialUpgraded(true);
      // ADR-0014：套餐交付后，有已开聊试用码且未「不再提醒」→ 弹消耗升级（每单只判一次）
      const isPackage =
        ord.product_type === 'quarterly_package' || ord.product_type === 'annual_package';
      if (isPackage && !ord.meta?.auto_upgraded && !upgradeCheckedRef.current) {
        upgradeCheckedRef.current = true;
        getUpgradeContext()
          .then((ctx) => {
            if (ctx.has_started_trial && !ctx.dont_remind && (ctx.unbound_codes ?? []).length > 0) {
              setUpgradeOpen(true);
            }
          })
          .catch(() => {
            /* 上下文拉取失败静默，不弹 */
          });
      }
      return true;
    }
    if (ord.status === 'closed' || ord.status === 'cancelled' || ord.status === 'refunded') {
      setView('closed');
      return true;
    }
    // pending / paid：继续确认中
    setView('confirming');
    return false;
  }, []);

  // ── 首次按订单号查询 ──
  useEffect(() => {
    if (!outTradeNo) return;
    deadlineRef.current = Date.now() + CONFIRM_TIMEOUT_MS;
    // sync=true：后端实时向支付宝查单核实（每单 10s 冷却）
    getOrderByNo(outTradeNo, true)
      .then((res) => applyOrder(res.order))
      .catch((e: unknown) => {
        setError(
          isAuthError(e)
            ? t('payment.result.authExpired')
            : getApiErrorMessage(e, t('payment.result.loadFailed')),
        );
        setView('error');
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outTradeNo]);

  // ── 确认中：每 2s 轮询，直到终态或 30 分钟超时 ──
  useEffect(() => {
    if (view !== 'confirming' || !outTradeNo) return;
    const timer = setInterval(async () => {
      if (Date.now() > deadlineRef.current) {
        clearInterval(timer);
        setView('closed');
        return;
      }
      try {
        // sync=true：后端实时向支付宝查单核实（每单 10s 冷却，2s 轮询可放心携带）
        const res = await getOrderByNo(outTradeNo, true);
        if (applyOrder(res.order)) clearInterval(timer);
      } catch (e: unknown) {
        if (isAuthError(e)) {
          // 登录态失效：停止轮询并提示重新登录（否则会永远卡在「确认中」）
          clearInterval(timer);
          setError(t('payment.result.authExpired'));
          setView('error');
        }
        /* 其他单次轮询失败静默，等待下次 */
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, outTradeNo, applyOrder]);

  const handleCopyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 1500);
    } catch {
      /* 复制失败静默 */
    }
  };

  const handleGoOrders = () => router.push('/dashboard/orders');

  const handleGoConsultation = () => {
    const bookingId = order?.meta?.booking_id;
    router.push(bookingId ? `/dashboard/consultation/${bookingId}` : '/dashboard/orders');
  };

  // 套餐交付的全部码（等价、不区分用途）；弹窗升级后排除已消耗的那枚
  const allDeliveredCodes: string[] = order?.meta?.codes?.length
    ? order.meta.codes
    : [order?.delivered_code, ...(order?.meta?.gift_codes ?? [])].filter(
        (c): c is string => !!c,
      );
  const availableCodes = allDeliveredCodes.filter((c) => c && c !== consumedCode);
  const giftCodes = availableCodes.filter((c) => c !== order?.delivered_code);

  return (
    <div className="mx-auto max-w-md px-5 py-16">
      <h1 className="mb-6 text-2xl font-semibold text-bd-fg">{t('payment.result.title')}</h1>

      <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-8">
        {(view === 'loading' || view === 'confirming') && (
          <div className="flex flex-col items-center space-y-4 py-6 text-center">
            <Loader2 className="h-10 w-10 animate-spin text-bd-subtle" />
            <p className="text-sm font-medium text-bd-fg">{t('payment.result.confirming')}</p>
            <p className="text-xs text-bd-muted">{t('payment.result.confirmingHint')}</p>
          </div>
        )}

        {view === 'granted' && order && (
          <div className="flex flex-col items-center space-y-5 py-2 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
              <Check className="h-6 w-6 text-emerald-600" strokeWidth={2.5} />
            </div>
            <p className="text-base font-semibold text-bd-fg">{t('payment.success.title')}</p>

            {order.product_type === 'renewal' ? (
              /* 延期成功：展示目标码与追加天数 */
              <>
                <div className="space-y-1">
                  <p className="text-xs text-bd-muted">{t('payment.renewal.targetLabel')}</p>
                  <p className="font-mono text-2xl font-bold tracking-widest text-bd-fg">
                    {order.meta?.target_code ?? '—'}
                  </p>
                </div>
                {order.meta?.added_days != null && (
                  <p className="text-sm font-medium text-emerald-600">
                    {t('payment.success.addedDays', { days: String(order.meta.added_days) })}
                  </p>
                )}
                <button
                  type="button"
                  onClick={handleGoOrders}
                  className="w-full rounded-xl px-4 py-3.5 text-base font-semibold bg-bd-ui-accent text-bd-ui-accent-fg transition hover:opacity-90"
                >
                  {t('payment.success.done')}
                </button>
              </>
            ) : order.product_type === 'consultation' ? (
              /* 咨询购买成功：引导填写预约问卷 */
              <>
                <p className="text-sm leading-relaxed text-bd-muted">
                  {t('payment.success.consultationNote')}
                </p>
                <button
                  type="button"
                  onClick={handleGoConsultation}
                  className="w-full rounded-xl px-4 py-3.5 text-base font-semibold bg-bd-ui-accent text-bd-ui-accent-fg transition hover:opacity-90"
                >
                  {t('payment.success.consultationCta')}
                </button>
              </>
            ) : trialUpgraded ? (
              /* 试用码已升级为完整版（直购自动升级 / 弹窗消耗升级） */
              <>
                <p className="text-sm font-medium leading-relaxed text-emerald-600">
                  {t('payment.success.autoUpgradedNote')}
                </p>
                {availableCodes.length > 0 && (
                  <div className="w-full space-y-2 rounded-xl border border-amber-200/80 bg-amber-50/60 px-4 py-3.5 text-left">
                    <p className="text-xs font-medium text-bd-fg">
                      {t('payment.success.codesLabel', {
                        count: String(availableCodes.length),
                      })}
                    </p>
                    {availableCodes.map((code) => (
                      <CopyableCode
                        key={code}
                        code={code}
                        copiedCode={copiedCode}
                        onCopy={(c) => void handleCopyCode(c)}
                        t={t}
                      />
                    ))}
                    <p className="text-[11px] leading-relaxed text-bd-muted">
                      {t('payment.success.giftNote')}
                    </p>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => router.push('/explore')}
                  className="w-full rounded-xl px-4 py-3.5 text-base font-semibold bg-bd-ui-accent text-bd-ui-accent-fg transition hover:opacity-90"
                >
                  {t('payment.success.continueExplore')}
                </button>
              </>
            ) : availableCodes.length > 1 ? (
              /* 多码套餐：全部码平级展示，不指定「哪枚自用/哪枚转赠」（码是等价的） */
              <>
                <div className="w-full space-y-2 rounded-xl border border-amber-200/80 bg-amber-50/60 px-4 py-3.5 text-left">
                  <p className="text-xs font-medium text-bd-fg">
                    {t('payment.success.codesLabel', { count: String(availableCodes.length) })}
                  </p>
                  {availableCodes.map((code) => (
                    <CopyableCode
                      key={code}
                      code={code}
                      copiedCode={copiedCode}
                      onCopy={(c) => void handleCopyCode(c)}
                      t={t}
                    />
                  ))}
                  <p className="text-[11px] leading-relaxed text-bd-muted">
                    {t('payment.success.giftNote')}
                  </p>
                </div>
                <p className="text-xs text-bd-subtle">{t('payment.success.emailNote')}</p>
                <button
                  type="button"
                  onClick={() =>
                    order.delivered_code &&
                    router.push(`/explore/activate?code=${encodeURIComponent(order.delivered_code)}`)
                  }
                  disabled={!order.delivered_code}
                  className="w-full rounded-xl px-4 py-3.5 text-base font-semibold bg-bd-ui-accent text-bd-ui-accent-fg transition hover:opacity-90 disabled:opacity-40"
                >
                  {t('payment.success.activate')}
                </button>
              </>
            ) : (
              /* 单码订单（季度套餐/旧 SKU）：交付码（未绑定） */
              <>
                <div className="space-y-1">
                  <p className="text-xs text-bd-muted">{t('payment.success.codeLabel')}</p>
                  <p className="font-mono text-2xl font-bold tracking-widest text-bd-fg">
                    {order.delivered_code ?? '—'}
                  </p>
                </div>
                {order.delivered_code && (
                  <button
                    type="button"
                    onClick={() => void handleCopyCode(order.delivered_code!)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-bd-border px-3 py-1.5 text-xs font-medium text-bd-muted transition hover:text-bd-fg"
                  >
                    {copiedCode === order.delivered_code ? (
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
                )}
                {giftCodes.length > 0 && (
                  <div className="w-full space-y-2 rounded-xl border border-amber-200/80 bg-amber-50/60 px-4 py-3.5 text-left">
                    <p className="text-xs font-medium text-bd-fg">
                      {t('payment.success.giftCodesLabel')}
                    </p>
                    {giftCodes.map((code) => (
                      <CopyableCode
                        key={code}
                        code={code}
                        copiedCode={copiedCode}
                        onCopy={(c) => void handleCopyCode(c)}
                        t={t}
                      />
                    ))}
                    <p className="text-[11px] leading-relaxed text-bd-muted">
                      {t('payment.success.giftNote')}
                    </p>
                  </div>
                )}
                <p className="text-xs text-bd-subtle">{t('payment.success.emailNote')}</p>
                <button
                  type="button"
                  onClick={() =>
                    order.delivered_code &&
                    router.push(`/explore/activate?code=${encodeURIComponent(order.delivered_code)}`)
                  }
                  disabled={!order.delivered_code}
                  className="w-full rounded-xl px-4 py-3.5 text-base font-semibold bg-bd-ui-accent text-bd-ui-accent-fg transition hover:opacity-90 disabled:opacity-40"
                >
                  {t('payment.success.activate')}
                </button>
              </>
            )}
          </div>
        )}

        {(view === 'closed' || view === 'error' || view === 'invalid') && (
          <div className="flex flex-col items-center space-y-4 py-6 text-center">
            <XCircle className="h-10 w-10 text-red-400" />
            <p className="text-sm font-medium text-bd-fg">
              {view === 'invalid'
                ? t('payment.result.invalid')
                : view === 'error'
                  ? t('payment.result.loadFailed')
                  : t('payment.result.closed')}
            </p>
            <p className="text-xs text-bd-muted">
              {view === 'invalid'
                ? t('payment.result.invalidHint')
                : view === 'error'
                  ? error
                  : t('payment.result.closedHint')}
            </p>
            <button
              type="button"
              onClick={handleGoOrders}
              className="rounded-xl px-6 py-2.5 text-sm font-semibold bg-bd-ui-accent text-bd-ui-accent-fg transition hover:opacity-90"
            >
              {view === 'closed' ? t('payment.result.repurchase') : t('payment.result.viewOrders')}
            </button>
          </div>
        )}
      </div>
      <UpgradeTrialModal
        open={upgradeOpen}
        onClose={() => setUpgradeOpen(false)}
        onUpgraded={(_trialCode, consumed) => {
          setUpgradeOpen(false);
          setTrialUpgraded(true);
          setConsumedCode(consumed ?? null);
        }}
        preferredCodes={order?.meta?.codes}
        showDontRemind
      />
    </div>
  );
}

export default function PaymentResultPage() {
  return (
    <Suspense fallback={null}>
      <PaymentResultContent />
    </Suspense>
  );
}
