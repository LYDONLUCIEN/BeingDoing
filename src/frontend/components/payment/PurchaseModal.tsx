'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Copy, Loader2, X } from 'lucide-react';
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
import { useLocale } from '@/hooks/useLocale';
import { CopyableCode } from '@/components/payment/CopyableCode';
import UpgradeTrialModal from '@/components/payment/UpgradeTrialModal';
import { TeamAnalysisNoticeBox } from '@/components/payment/TeamAnalysisNoticeModal';
import { getUpgradeContext } from '@/lib/api/activation';

export type PurchaseModalProps = {
  open: boolean;
  onClose: () => void;
  /** 支付成功（含 0 元单直接发放）时回调交付的激活码与订单（renewal/consultation 无新码则不触发） */
  onSuccess?: (code: string, order: OrderItem) => void;
  /** 「继续支付」：打开即拉取该订单并直接进入支付视图 */
  resumeOrderId?: string;
  /** 下单视图默认选中的商品（如 dashboard 购买卡默认年度套餐） */
  defaultProductType?: ProductType;
  /** 传入即进入「激活码延期」模式：跳过商品选择，直接渠道 + 券码下单 */
  renewalTargetCode?: string;
  /** 订单意图（ADR-0014）：试用拦截点直购升级——支付成功后后端自动消耗 1 码升级试用码 */
  intent?: 'upgrade_trial';
};

type ViewState = 'order' | 'waiting' | 'success';

/** 等待支付视图的子状态：轮询中 / 订单已关闭 / 订单已过期 */
type WaitStatus = 'polling' | 'closed' | 'expired';

/** 订单状态轮询间隔 */
const POLL_INTERVAL_MS = 2000;

/** 订单等待超时（与后端 ORDER_TIMEOUT_MINUTES 对应） */
const ORDER_TIMEOUT_MS = 30 * 60 * 1000;

/** 下单视图可选的套餐类型（咨询走报告页入口，P-D） */
const PACKAGE_TYPES: ProductType[] = ['quarterly_package', 'annual_package'];

/** 商品信息加载失败时的兜底（与后端默认配置一致），保证弹窗可用 */
const FALLBACK_PRODUCTS: ProductItem[] = [
  {
    product_type: 'quarterly_package',
    name: '季度套餐',
    description: '不限量对话 · 全部 5 阶段 · 1 份完整报告 + 人工审核',
    price: 6900,
    duration_days: 90,
    popular: true,
  },
  {
    product_type: 'annual_package',
    name: '年度套餐',
    description: '3 份完整报告 · 3 个激活码（可自用可转赠） · 团队分析 · 人工审核',
    price: 15900,
    duration_days: 365,
  },
  {
    product_type: 'consultation',
    name: '报告解读咨询',
    description: '一对一线上沟通（约 60 分钟）',
    price: 29800,
  },
];

/**
 * 购买套餐弹窗（P-B 套餐商品化；P2a 支付宝闭环）
 * 三视图：下单（套餐选择/延期激活 + 渠道 + 券码）→ 等待支付（新标签页打开支付宝收银台，本页轮询订单状态）→ 成功（0 元单直接发码 / 轮询到 granted）
 * 支付宝同步回跳页 /payment/result 仍保留，作为新标签页付完款后的落地页。
 * 弹层模式与 LegalDocModal 一致：fixed inset-0 z-[210]、ESC/遮罩关闭、锁定背景滚动。
 */
export default function PurchaseModal({
  open,
  onClose,
  onSuccess,
  resumeOrderId,
  defaultProductType,
  renewalTargetCode,
  intent,
}: PurchaseModalProps) {
  const router = useRouter();
  const { t } = useLocale();

  const renewalMode = Boolean(renewalTargetCode);
  /** 咨询专属模式：跳过套餐选择，直接展示咨询卡片下单（修复 F3：兜底错选季度套餐导致界面价与实际收款不符） */
  const consultationMode = !renewalMode && defaultProductType === 'consultation';

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
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  /** 等待支付视图：收银台 URL（「如果没有弹出，请点击这里」重开用） */
  const [payUrl, setPayUrl] = useState<string | null>(null);
  const [waitStatus, setWaitStatus] = useState<WaitStatus>('polling');
  /** 消耗升级弹窗（ADR-0014）：套餐成功交付且有已开聊试用码时弹出 */
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  /** 消耗升级完成（本弹窗内或后端直购自动升级）：成功视图切换为「已升级」态 */
  const [trialUpgraded, setTrialUpgraded] = useState(false);
  /** 弹窗消耗升级实际用掉的付费码（从展示列表排除） */
  const [consumedCode, setConsumedCode] = useState<string | null>(null);

  const successFiredRef = useRef(false);

  const selectedProduct =
    products.find((p) => p.product_type === selectedType) ?? products[0] ?? FALLBACK_PRODUCTS[0];
  /** 咨询模式单独定价：优先接口价，兜底 ¥298 */
  const consultationProduct =
    products.find((p) => p.product_type === 'consultation') ?? FALLBACK_PRODUCTS[2];
  const priceProduct = consultationMode ? consultationProduct : selectedProduct;
  // 延期模式价格由后端按码类型定价，前端下单前不展示确定金额
  const finalAmount = Math.max(0, priceProduct.price - (appliedCoupon?.amount ?? 0));

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
      if (ord.meta?.auto_upgraded) setTrialUpgraded(true);
      if (!successFiredRef.current) {
        successFiredRef.current = true;
        if (ord.delivered_code) onSuccess?.(ord.delivered_code, ord);
      }
      // ADR-0014：套餐交付后，若有已开聊试用码且未「不再提醒」，弹消耗升级
      const isPackage =
        ord.product_type === 'quarterly_package' || ord.product_type === 'annual_package';
      if (isPackage && !ord.meta?.auto_upgraded) {
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
    },
    [onSuccess],
  );

  // ── 回到下单视图（重新下单/取消订单后）──
  const resetToOrderView = useCallback(() => {
    setView('order');
    setOrder(null);
    setAppliedCoupon(null);
    setCouponInput('');
    setCouponError(null);
    setError(null);
    setPayUrl(null);
    setWaitStatus('polling');
    setUpgradeOpen(false);
    setTrialUpgraded(false);
    successFiredRef.current = false;
  }, []);

  // ── 进入等待支付视图：新标签页打开收银台，本页保持上下文轮询 ──
  const startWaiting = useCallback((ord: OrderItem, url: string) => {
    setOrder(ord);
    setPayUrl(url);
    setWaitStatus('polling');
    setView('waiting');
    window.open(url, '_blank');
  }, []);

  // ── 等待支付：每 2s 轮询订单状态，直到发放/关闭/取消，或 30 分钟超时 ──
  // 视图切换或组件卸载时由 cleanup 清理 interval
  useEffect(() => {
    if (view !== 'waiting' || !order) return;
    const deadline = Date.now() + ORDER_TIMEOUT_MS;
    const timer = setInterval(async () => {
      if (Date.now() > deadline) {
        clearInterval(timer);
        setWaitStatus('expired');
        return;
      }
      try {
        // sync=true：后端实时向支付宝查单核实（每单 10s 冷却，2s 轮询可放心携带）
        const res = await getOrder(order.id, true);
        const st = res.order.status;
        if (st === 'granted') {
          clearInterval(timer);
          enterSuccess(res.order);
        } else if (st === 'closed' || st === 'cancelled' || st === 'refunded') {
          clearInterval(timer);
          setWaitStatus('closed');
        }
      } catch {
        /* 单次轮询失败静默，等待下次 */
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [view, order, enterSuccess]);

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
        const items = [...res.items];
        // 接口未返回咨询商品时补兜底（¥298），保证咨询模式可下单
        if (!items.some((it) => it.product_type === 'consultation')) {
          items.push(FALLBACK_PRODUCTS[2]);
        }
        if (items.some((it) => PACKAGE_TYPES.includes(it.product_type))) setProducts(items);
      })
      .catch(() => {
        /* 使用兜底商品信息 */
      });

    if (resumeOrderId) {
      getOrder(resumeOrderId)
        .then((res) => {
          const st = res.order.status;
          if ((st === 'pending' || st === 'paid') && res.pay_url) {
            // 继续支付：新标签页打开支付宝收银台
            startWaiting(res.order, res.pay_url);
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
          : consultationMode
            ? {
                product_type: 'consultation',
                channel,
                coupon_code: appliedCoupon?.code,
              }
            : {
                product_type: selectedType,
                channel,
                coupon_code: appliedCoupon?.code,
                intent,
              },
      );
      if (!res.payment || res.order.status === 'granted') {
        // 0 元单：直接发放
        enterSuccess(res.order);
      } else {
        // 新标签页打开支付宝收银台（本页轮询等待支付完成）
        startWaiting(res.order, res.payment.pay_url);
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
    router.push('/dashboard/codes?tab=orders');
  };

  /** 咨询购买成功：跳预约问卷页（无 booking_id 时兜底我的订单） */
  const handleGoConsultation = () => {
    onClose();
    const bookingId = order?.meta?.booking_id;
    router.push(bookingId ? `/dashboard/consultation/${bookingId}` : '/dashboard/codes?tab=orders');
  };

  const orderTitle = renewalMode
    ? t('payment.renewal.title')
    : consultationMode
      ? t('payment.consultation.title')
      : t('payment.title');
  // 套餐交付的全部码（等价、不区分用途）；弹窗升级后排除已消耗的那枚
  const allDeliveredCodes: string[] = order?.meta?.codes?.length
    ? order.meta.codes
    : [order?.delivered_code, ...(order?.meta?.gift_codes ?? [])].filter(
        (c): c is string => !!c,
      );
  const availableCodes = allDeliveredCodes.filter((c) => c && c !== consumedCode);
  const giftCodes = availableCodes.filter((c) => c !== order?.delivered_code);

  return (
    <>
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
                {view === 'waiting'
                  ? t('payment.waiting.title')
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
                  ) : consultationMode ? (
                    /* 报告解读咨询：专属卡片，跳过套餐选择 */
                    <div className="rounded-xl border border-stone-200/80 bg-stone-50/60 px-4 py-4">
                      <p className="text-[15px] font-semibold text-stone-800">
                        {t('payment.consultation.name') !== 'payment.consultation.name'
                          ? t('payment.consultation.name')
                          : consultationProduct.name}
                      </p>
                      <p className="mt-1.5">
                        <span className="text-xl font-bold text-stone-900">
                          ¥{fenToYuan(consultationProduct.price)}
                        </span>
                        <span className="ml-1 text-xs text-stone-500">
                          / {t('payment.consultation.period')}
                        </span>
                      </p>
                      <p className="mt-2.5 text-xs leading-relaxed text-stone-500">
                        {t('payment.consultation.desc')}
                      </p>
                    </div>
                  ) : (
                    /* 套餐选择：季度套餐 / 年度套餐 */
                    <div className="grid grid-cols-2 gap-3">
                      {products.filter((p) => PACKAGE_TYPES.includes(p.product_type)).map((p) => {
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
                          <span>¥{fenToYuan(priceProduct.price)}</span>
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

              {view === 'waiting' && order && (
                /* 等待支付：收银台已在新标签页打开，本页轮询订单状态 */
                <div className="space-y-5">
                  {waitStatus === 'polling' ? (
                    <div className="flex flex-col items-center space-y-3 py-6 text-center">
                      <Loader2 className="h-8 w-8 animate-spin text-stone-400" />
                      <p className="text-sm font-medium leading-relaxed text-stone-700">
                        {t('payment.waiting.hint')}
                      </p>
                      <button
                        type="button"
                        onClick={() => payUrl && window.open(payUrl, '_blank')}
                        className="text-xs text-[#1677ff] underline-offset-2 transition hover:underline"
                      >
                        {t('payment.waiting.reopen')}
                      </button>
                    </div>
                  ) : (
                    /* 订单已关闭/已过期：引导重新下单 */
                    <div className="flex flex-col items-center space-y-3 py-6 text-center">
                      <p className="text-sm font-medium text-stone-700">
                        {waitStatus === 'expired'
                          ? t('payment.waiting.expired')
                          : t('payment.waiting.closed')}
                      </p>
                      <button
                        type="button"
                        onClick={resetToOrderView}
                        className="rounded-xl bg-stone-900 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-stone-800"
                      >
                        {t('payment.waiting.reorder')}
                      </button>
                    </div>
                  )}
                  <div className="flex items-center justify-between border-t border-stone-200/70 pt-4 text-sm">
                    <span className="text-stone-500">{t('payment.price.final')}</span>
                    <span className="text-lg font-bold text-stone-900">
                      ¥{fenToYuan(order.amount_paid)}
                    </span>
                  </div>
                  {error && <p className="text-sm text-red-600">{error}</p>}
                  {waitStatus === 'polling' && (
                    <div className="text-center">
                      <button
                        type="button"
                        onClick={() => void handleCancelOrder()}
                        className="text-xs text-stone-400 underline-offset-2 transition hover:text-stone-600 hover:underline"
                      >
                        {t('payment.waiting.cancel')}
                      </button>
                    </div>
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
                  ) : trialUpgraded ? (
                    /* 试用码已升级为完整版（直购自动升级 / 弹窗消耗升级） */
                    <>
                      <p className="text-sm font-medium leading-relaxed text-emerald-600">
                        {t('payment.success.autoUpgradedNote')}
                      </p>
                      {availableCodes.length > 0 && (
                        <div className="w-full space-y-2 rounded-xl border border-amber-200/80 bg-amber-50/60 px-4 py-3.5 text-left">
                          <p className="text-xs font-medium text-stone-700">
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
                          <p className="text-[11px] leading-relaxed text-stone-500">
                            {t('payment.success.giftNote')}
                          </p>
                        </div>
                      )}
                      {order.product_type === 'annual_package' && <TeamAnalysisNoticeBox />}
                      <button
                        type="button"
                        onClick={onClose}
                        className="w-full rounded-xl bg-stone-900 px-4 py-3.5 text-base font-semibold text-white transition hover:bg-stone-800"
                      >
                        {t('payment.success.continueExplore')}
                      </button>
                    </>
                  ) : availableCodes.length > 1 ? (
                    /* 多码套餐：全部码平级展示，不指定「哪枚自用/哪枚转赠」（码是等价的） */
                    <>
                      <div className="w-full space-y-2 rounded-xl border border-amber-200/80 bg-amber-50/60 px-4 py-3.5 text-left">
                        <p className="text-xs font-medium text-stone-700">
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
                        <p className="text-[11px] leading-relaxed text-stone-500">
                          {t('payment.success.giftNote')}
                        </p>
                      </div>
                      {order.product_type === 'annual_package' && <TeamAnalysisNoticeBox />}
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
                  ) : (
                    /* 单码订单（季度套餐/旧 SKU）：交付码（未绑定） */
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
    </>
  );
}
