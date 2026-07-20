'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { QRCodeSVG } from 'qrcode.react';
import { Check, Copy, X } from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  cancelOrder,
  createOrder,
  fenToYuan,
  getOrder,
  getProducts,
  validateCoupon,
  type OrderItem,
  type PayChannel,
  type ProductItem,
  type ProductType,
} from '@/lib/api/payment';
import { toDate } from '@/lib/utils/formatTime';
import { useLocale } from '@/hooks/useLocale';

export type PurchaseModalProps = {
  open: boolean;
  onClose: () => void;
  /** 支付成功（含 0 元单直接发放）时回调交付的激活码（renewal/consultation 无新码则不触发） */
  onSuccess?: (code: string) => void;
  /** 「继续支付」：打开即拉取该订单并直接进入支付视图 */
  resumeOrderId?: string;
  /** 下单视图默认选中的商品（如 dashboard 购买卡默认年度卡） */
  defaultProductType?: ProductType;
  /** 传入即进入「延期激活」模式：跳过商品选择，直接渠道 + 券码下单 */
  renewalTargetCode?: string;
};

type ViewState = 'order' | 'paying' | 'success';

const ORDER_TIMEOUT_MS = 30 * 60 * 1000;
const POLL_INTERVAL_MS = 2000;

/** 下单视图可选的套餐类型（咨询走报告页入口，P-D） */
const PACKAGE_TYPES: ProductType[] = ['quarterly_package', 'annual_package'];

/** 商品信息加载失败时的兜底（与后端默认配置一致），保证弹窗可用 */
const FALLBACK_PRODUCTS: ProductItem[] = [
  {
    product_type: 'quarterly_package',
    name: '季度卡',
    description: '不限量对话 · 全部 5 阶段 · 1 份报告 + 人工审核',
    price: 6900,
    duration_days: 90,
  },
  {
    product_type: 'annual_package',
    name: '年度卡',
    description: '3 份报告 · 2 个赠品码 · 团队分析 · 人工审核',
    price: 9900,
    duration_days: 365,
    popular: true,
  },
];

function formatCountdown(ms: number): string {
  const totalSec = Math.ceil(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/** 单个可复制码行（自己的码 / 赠品码共用） */
function CopyableCode({
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

/**
 * 购买套餐弹窗（P-B 套餐商品化；P2a 支付宝闭环）
 * 三视图：下单（套餐选择/延期激活 + 渠道 + 券码）→ 支付（二维码 + 倒计时 + 轮询）→ 成功（码/赠品码/延期天数）
 * 弹层模式与 LegalDocModal 一致：fixed inset-0 z-[210]、ESC/遮罩关闭、锁定背景滚动。
 */
export default function PurchaseModal({
  open,
  onClose,
  onSuccess,
  resumeOrderId,
  defaultProductType,
  renewalTargetCode,
}: PurchaseModalProps) {
  const router = useRouter();
  const { t } = useLocale();

  const renewalMode = Boolean(renewalTargetCode);

  const [view, setView] = useState<ViewState>('order');
  const [products, setProducts] = useState<ProductItem[]>(FALLBACK_PRODUCTS);
  const [selectedType, setSelectedType] = useState<ProductType>(
    defaultProductType ?? 'annual_package',
  );
  const [channel, setChannel] = useState<PayChannel>('alipay');
  const [couponInput, setCouponInput] = useState('');
  const [appliedCoupon, setAppliedCoupon] = useState<{ code: string; amount: number } | null>(null);
  const [couponError, setCouponError] = useState<string | null>(null);
  const [couponChecking, setCouponChecking] = useState(false);
  const [order, setOrder] = useState<OrderItem | null>(null);
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remainMs, setRemainMs] = useState(ORDER_TIMEOUT_MS);
  const [orderClosed, setOrderClosed] = useState(false);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const successFiredRef = useRef(false);

  const selectedProduct =
    products.find((p) => p.product_type === selectedType) ?? products[0] ?? FALLBACK_PRODUCTS[0];
  // 延期模式价格由后端按码类型定价，前端下单前不展示确定金额
  const finalAmount = Math.max(0, selectedProduct.price - (appliedCoupon?.amount ?? 0));

  /** 套餐特性文案（i18n 缺失的键自动跳过） */
  const planFeatures = (type: ProductType): string[] =>
    ['f1', 'f2', 'f3', 'f4']
      .map((f) => {
        const key = `payment.plan.${type}.${f}`;
        const val = t(key);
        return val === key ? null : val;
      })
      .filter((v): v is string => Boolean(v));

  // ── 进入成功视图（onSuccess 每单只触发一次）──
  const enterSuccess = useCallback(
    (ord: OrderItem) => {
      setOrder(ord);
      setView('success');
      if (!successFiredRef.current) {
        successFiredRef.current = true;
        if (ord.delivered_code) onSuccess?.(ord.delivered_code);
      }
    },
    [onSuccess],
  );

  // ── 回到下单视图（重新下单/取消订单后）──
  const resetToOrderView = useCallback(() => {
    setView('order');
    setOrder(null);
    setQrCode(null);
    setOrderClosed(false);
    setAppliedCoupon(null);
    setCouponInput('');
    setCouponError(null);
    setError(null);
    setRemainMs(ORDER_TIMEOUT_MS);
    successFiredRef.current = false;
  }, []);

  // ── ESC 关闭 + 锁定背景滚动（同 LegalDocModal）──
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  // ── 打开时初始化：拉商品；resumeOrderId 直接进入支付/成功视图 ──
  useEffect(() => {
    if (!open) return;
    resetToOrderView();
    setCopiedCode(null);
    setSelectedType(defaultProductType ?? 'annual_package');

    getProducts()
      .then((res) => {
        const packages = res.items.filter((it) => PACKAGE_TYPES.includes(it.product_type));
        if (packages.length > 0) setProducts(packages);
      })
      .catch(() => {
        /* 使用兜底商品信息 */
      });

    if (resumeOrderId) {
      getOrder(resumeOrderId)
        .then((res) => {
          const st = res.order.status;
          if (st === 'pending' || st === 'paid') {
            setOrder(res.order);
            setQrCode(res.qr_code);
            setView('paying');
          } else if (st === 'granted') {
            enterSuccess(res.order);
          } else {
            setError(t('payment.error.resume'));
          }
        })
        .catch((e: unknown) => {
          setError(getApiErrorMessage(e, t('payment.error.resume')));
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resumeOrderId, defaultProductType]);

  // ── 支付视图：30:00 倒计时（order.created_at + 30 分钟）──
  useEffect(() => {
    if (!open || view !== 'paying' || !order) return;
    const created = toDate(order.created_at)?.getTime() ?? Date.now();
    const deadline = created + ORDER_TIMEOUT_MS;
    const tick = () => setRemainMs(Math.max(0, deadline - Date.now()));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [open, view, order]);

  // ── 支付视图：每 2s 轮询订单状态 ──
  useEffect(() => {
    if (!open || view !== 'paying' || !order || orderClosed) return;
    const timer = setInterval(async () => {
      try {
        const res = await getOrder(order.id);
        const st = res.order.status;
        if (st === 'granted') {
          enterSuccess(res.order);
        } else if (st === 'closed' || st === 'cancelled') {
          setOrder(res.order);
          setOrderClosed(true);
        } else {
          setOrder(res.order);
        }
      } catch {
        /* 单次轮询失败静默，等待下次 */
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [open, view, order, orderClosed, enterSuccess]);

  // ── 券码校验 ──
  const handleApplyCoupon = async () => {
    const code = couponInput.trim();
    if (!code || couponChecking) return;
    setCouponChecking(true);
    setCouponError(null);
    try {
      const res = await validateCoupon(code);
      setAppliedCoupon({ code: res.code, amount: res.amount });
    } catch (e: unknown) {
      setAppliedCoupon(null);
      setCouponError(getApiErrorMessage(e, t('payment.coupon.invalid')));
    } finally {
      setCouponChecking(false);
    }
  };

  // ── 下单 ──
  const handlePay = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await createOrder(
        renewalMode
          ? {
              product_type: 'renewal',
              channel,
              coupon_code: appliedCoupon?.code,
              target_code: renewalTargetCode,
            }
          : {
              product_type: selectedType,
              channel,
              coupon_code: appliedCoupon?.code,
            },
      );
      if (!res.payment || res.order.status === 'granted') {
        // 0 元单：直接发放
        enterSuccess(res.order);
      } else {
        setOrder(res.order);
        setQrCode(res.payment.qr_code);
        setView('paying');
      }
    } catch (e: unknown) {
      setError(getApiErrorMessage(e, t('payment.error.createOrder')));
    } finally {
      setSubmitting(false);
    }
  };

  // ── 取消订单 ──
  const handleCancelOrder = async () => {
    if (!order) return;
    if (!window.confirm(t('payment.confirmCancel'))) return;
    try {
      await cancelOrder(order.id);
      resetToOrderView();
    } catch (e: unknown) {
      setError(getApiErrorMessage(e, t('payment.error.cancel')));
    }
  };

  const handleCopyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 1500);
    } catch {
      /* 复制失败静默 */
    }
  };

  const handleGoActivate = (code: string) => {
    onClose();
    router.push(`/explore/activate?code=${encodeURIComponent(code)}`);
  };

  const handleGoOrders = () => {
    onClose();
    router.push('/dashboard/orders');
  };

  /** 咨询购买成功：跳预约问卷页（无 booking_id 时兜底我的订单） */
  const handleGoConsultation = () => {
    onClose();
    const bookingId = order?.meta?.booking_id;
    router.push(bookingId ? `/dashboard/consultation/${bookingId}` : '/dashboard/orders');
  };

  const expired = remainMs <= 0;

  const orderTitle = renewalMode ? t('payment.renewal.title') : t('payment.title');
  const giftCodes = order?.meta?.gift_codes ?? [];

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
            aria-labelledby="purchase-modal-title"
            className="relative w-full max-w-md max-h-[85vh] flex flex-col rounded-2xl border border-stone-200/80 bg-white/95 shadow-[0_24px_80px_-24px_rgba(15,23,42,0.18),0_0_0_1px_rgba(255,255,255,0.6)_inset]"
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* 标题栏 + 关闭按钮 */}
            <div className="flex items-center justify-between gap-4 px-6 py-4 border-b border-stone-200/70">
              <h2 id="purchase-modal-title" className="text-lg font-semibold tracking-tight text-stone-800">
                {view === 'paying'
                  ? t('payment.paying.title')
                  : view === 'success'
                    ? t('payment.success.title')
                    : orderTitle}
              </h2>
              <button
                type="button"
                onClick={onClose}
                aria-label="关闭"
                className="shrink-0 rounded-full p-1.5 text-stone-500 hover:bg-stone-100 hover:text-stone-700 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-stone-400/60"
              >
                <X className="w-[18px] h-[18px]" />
              </button>
            </div>

            <div className="overflow-y-auto px-6 py-5">
              {view === 'order' && (
                <div className="space-y-5">
                  {renewalMode ? (
                    /* 延期激活：跳过商品选择，价格由后端按码类型定价 */
                    <div className="rounded-xl border border-stone-200/80 bg-stone-50/60 px-4 py-4">
                      <p className="text-xs text-stone-500">{t('payment.renewal.targetLabel')}</p>
                      <p className="mt-1 font-mono text-base font-semibold tracking-widest text-stone-900">
                        {renewalTargetCode}
                      </p>
                      <p className="mt-2 text-xs leading-relaxed text-stone-500">
                        {t('payment.renewal.priceHint')}
                      </p>
                    </div>
                  ) : (
                    /* 套餐选择：季度卡 / 年度卡 */
                    <div className="grid grid-cols-2 gap-3">
                      {products.map((p) => {
                        const selected = p.product_type === selectedType;
                        const features = planFeatures(p.product_type);
                        return (
                          <button
                            key={p.product_type}
                            type="button"
                            onClick={() => setSelectedType(p.product_type)}
                            className={`relative rounded-xl border px-4 py-4 text-left transition ${
                              selected
                                ? 'border-stone-900 bg-stone-900/[0.03] ring-1 ring-stone-900/60'
                                : 'border-stone-200 bg-stone-50/60 hover:bg-stone-100/60'
                            }`}
                          >
                            {p.popular && (
                              <span className="absolute -top-2.5 right-3 rounded-full bg-amber-500 px-2 py-0.5 text-[10px] font-semibold text-white">
                                {t('payment.plan.popular')}
                              </span>
                            )}
                            <p className="text-[15px] font-semibold text-stone-800">
                              {t(`payment.plan.${p.product_type}.name`) !==
                              `payment.plan.${p.product_type}.name`
                                ? t(`payment.plan.${p.product_type}.name`)
                                : p.name}
                            </p>
                            <p className="mt-1.5">
                              <span className="text-xl font-bold text-stone-900">
                                ¥{fenToYuan(p.price)}
                              </span>
                              <span className="ml-1 text-xs text-stone-500">
                                / {t(`payment.plan.${p.product_type}.period`)}
                              </span>
                            </p>
                            <ul className="mt-2.5 space-y-1">
                              {(features.length > 0
                                ? features
                                : (p.features ?? []).slice(0, 4)
                              ).map((f) => (
                                <li
                                  key={f}
                                  className="flex items-start gap-1.5 text-[11px] leading-snug text-stone-500"
                                >
                                  <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" strokeWidth={2.5} />
                                  {f}
                                </li>
                              ))}
                            </ul>
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* 渠道选择 */}
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-stone-600">{t('payment.channelLabel')}</p>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setChannel('alipay')}
                        className={`rounded-xl border px-3 py-2.5 text-sm font-medium transition ${
                          channel === 'alipay'
                            ? 'border-[#1677ff] bg-[#1677ff]/5 text-[#1677ff] ring-1 ring-[#1677ff]/30'
                            : 'border-stone-200 text-stone-600 hover:bg-stone-50'
                        }`}
                      >
                        {t('payment.channel.alipay')}
                      </button>
                      <button
                        type="button"
                        disabled
                        title={t('payment.channel.comingSoon')}
                        className="relative rounded-xl border border-stone-200 px-3 py-2.5 text-sm font-medium text-stone-400 cursor-not-allowed bg-stone-50/50"
                      >
                        {t('payment.channel.wechat')}
                        <span className="absolute -top-2 right-2 rounded-full bg-stone-200 px-1.5 py-0.5 text-[10px] text-stone-500">
                          {t('payment.channel.comingSoon')}
                        </span>
                      </button>
                    </div>
                  </div>

                  {/* 券码 */}
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={couponInput}
                        onChange={(e) => {
                          setCouponInput(e.target.value);
                          setCouponError(null);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void handleApplyCoupon();
                        }}
                        placeholder={t('payment.coupon.placeholder')}
                        className="flex-1 min-w-0 rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 text-sm text-stone-800 outline-none transition focus:border-stone-400"
                      />
                      <button
                        type="button"
                        onClick={() => void handleApplyCoupon()}
                        disabled={couponChecking || !couponInput.trim()}
                        className="shrink-0 rounded-xl border border-stone-300 px-4 py-2.5 text-sm font-medium text-stone-700 transition hover:bg-stone-100 disabled:opacity-40"
                      >
                        {couponChecking ? t('payment.coupon.checking') : t('payment.coupon.apply')}
                      </button>
                    </div>
                    {appliedCoupon && (
                      <p className="text-sm font-medium text-emerald-600">
                        {t('payment.coupon.applied', { amount: fenToYuan(appliedCoupon.amount) })}
                      </p>
                    )}
                    {couponError && <p className="text-sm text-red-600">{couponError}</p>}
                  </div>

                  {/* 金额行（延期模式价格下单后由后端确定，不展示确定金额） */}
                  <div className="space-y-1.5 border-t border-stone-200/70 pt-4">
                    {renewalMode ? (
                      <p className="text-xs text-stone-500">{t('payment.renewal.finalNote')}</p>
                    ) : (
                      <>
                        <div className="flex items-center justify-between text-sm text-stone-500">
                          <span>{t('payment.price.original')}</span>
                          <span>¥{fenToYuan(selectedProduct.price)}</span>
                        </div>
                        {appliedCoupon && (
                          <div className="flex items-center justify-between text-sm text-emerald-600">
                            <span>{t('payment.price.discount')}</span>
                            <span>-¥{fenToYuan(appliedCoupon.amount)}</span>
                          </div>
                        )}
                        <div className="flex items-end justify-between pt-1">
                          <span className="text-sm font-medium text-stone-700">
                            {t('payment.price.final')}
                          </span>
                          <span className="text-2xl font-bold text-stone-900">
                            ¥{fenToYuan(finalAmount)}
                          </span>
                        </div>
                      </>
                    )}
                  </div>

                  {error && <p className="text-sm text-red-600">{error}</p>}

                  {/* 主按钮 */}
                  <button
                    type="button"
                    onClick={() => void handlePay()}
                    disabled={submitting}
                    className="w-full rounded-xl bg-stone-900 px-4 py-3.5 text-base font-semibold text-white transition hover:bg-stone-800 disabled:opacity-40"
                  >
                    {submitting
                      ? t('payment.creating')
                      : renewalMode
                        ? t('payment.renewal.submit')
                        : finalAmount <= 0
                          ? t('payment.payFree')
                          : t('payment.pay', { amount: fenToYuan(finalAmount) })}
                  </button>
                </div>
              )}

              {view === 'paying' && order && (
                <div className="space-y-5">
                  {orderClosed || expired ? (
                    /* 已关闭/已过期：可重新下单 */
                    <div className="flex flex-col items-center py-6 text-center space-y-4">
                      <p className="text-sm text-stone-600">
                        {orderClosed ? t('payment.paying.closed') : t('payment.paying.expired')}
                      </p>
                      <button
                        type="button"
                        onClick={resetToOrderView}
                        className="rounded-xl bg-stone-900 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-stone-800"
                      >
                        {t('payment.paying.reorder')}
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="flex flex-col items-center space-y-3">
                        <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
                          {qrCode ? (
                            <QRCodeSVG value={qrCode} size={192} level="M" includeMargin={false} />
                          ) : (
                            <div className="flex h-48 w-48 items-center justify-center text-xs text-stone-400">
                              {t('payment.paying.qrLoading')}
                            </div>
                          )}
                        </div>
                        <p className="text-sm text-stone-600">{t('payment.paying.hint')}</p>
                        <p className="font-mono text-lg font-semibold tabular-nums text-stone-800">
                          {formatCountdown(remainMs)}
                        </p>
                        {order.status === 'paid' && (
                          <p className="text-sm text-emerald-600">{t('payment.paying.processing')}</p>
                        )}
                      </div>
                      <div className="flex items-center justify-between border-t border-stone-200/70 pt-4 text-sm">
                        <span className="text-stone-500">{t('payment.price.final')}</span>
                        <span className="text-lg font-bold text-stone-900">
                          ¥{fenToYuan(order.amount_paid)}
                        </span>
                      </div>
                      {error && <p className="text-sm text-red-600">{error}</p>}
                      <div className="text-center">
                        <button
                          type="button"
                          onClick={() => void handleCancelOrder()}
                          className="text-xs text-stone-400 underline-offset-2 transition hover:text-stone-600 hover:underline"
                        >
                          {t('payment.paying.cancel')}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {view === 'success' && order && (
                <div className="flex flex-col items-center space-y-5 py-2 text-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
                    <Check className="h-6 w-6 text-emerald-600" strokeWidth={2.5} />
                  </div>

                  {order.product_type === 'renewal' ? (
                    /* 延期成功：展示目标码与追加天数 */
                    <>
                      <div className="space-y-1">
                        <p className="text-xs text-stone-500">{t('payment.renewal.targetLabel')}</p>
                        <p className="font-mono text-2xl font-bold tracking-widest text-stone-900">
                          {order.meta?.target_code ?? renewalTargetCode ?? '—'}
                        </p>
                      </div>
                      {order.meta?.added_days != null && (
                        <p className="text-sm font-medium text-emerald-600">
                          {t('payment.success.addedDays', { days: String(order.meta.added_days) })}
                        </p>
                      )}
                      <button
                        type="button"
                        onClick={onClose}
                        className="w-full rounded-xl bg-stone-900 px-4 py-3.5 text-base font-semibold text-white transition hover:bg-stone-800"
                      >
                        {t('payment.success.done')}
                      </button>
                    </>
                  ) : order.product_type === 'consultation' ? (
                    /* 咨询购买成功：引导填写预约问卷 */
                    <>
                      <p className="text-sm leading-relaxed text-stone-600">
                        {t('payment.success.consultationNote')}
                      </p>
                      <button
                        type="button"
                        onClick={handleGoConsultation}
                        className="w-full rounded-xl bg-stone-900 px-4 py-3.5 text-base font-semibold text-white transition hover:bg-stone-800"
                      >
                        {t('payment.success.consultationCta')}
                      </button>
                    </>
                  ) : (
                    /* 套餐购买成功：自己的码 + 年度单赠品码 */
                    <>
                      <div className="space-y-1">
                        <p className="text-xs text-stone-500">{t('payment.success.codeLabel')}</p>
                        <p className="font-mono text-2xl font-bold tracking-widest text-stone-900">
                          {order.delivered_code ?? '—'}
                        </p>
                      </div>
                      {order.delivered_code && (
                        <button
                          type="button"
                          onClick={() => void handleCopyCode(order.delivered_code!)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-3 py-1.5 text-xs font-medium text-stone-600 transition hover:bg-stone-100"
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
                          <p className="text-xs font-medium text-stone-700">
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
                          <p className="text-[11px] leading-relaxed text-stone-500">
                            {t('payment.success.giftNote')}
                          </p>
                        </div>
                      )}
                      <p className="text-xs text-stone-400">{t('payment.success.emailNote')}</p>
                      <button
                        type="button"
                        onClick={() => order.delivered_code && handleGoActivate(order.delivered_code)}
                        disabled={!order.delivered_code}
                        className="w-full rounded-xl bg-stone-900 px-4 py-3.5 text-base font-semibold text-white transition hover:bg-stone-800 disabled:opacity-40"
                      >
                        {t('payment.success.activate')}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
