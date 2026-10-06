'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Check,
  ChevronDown,
  Copy,
  Loader2,
  X,
} from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  cancelOrder,
  createOrder,
  fenToYuan,
  getOrder,
  getProducts,
  listMyCoupons,
  validateCoupon,
  type MyCouponItem,
  type OrderItem,
  type PayChannel,
  type PayType,
  type ProductItem,
  type ProductType,
} from '@/lib/api/payment';
import { toDate } from '@/lib/utils/formatTime';
import { normalizeCouponCode } from '@/lib/codeFormat';
import { useLocale } from '@/hooks/useLocale';
import { CopyableCode } from '@/components/payment/CopyableCode';
import UpgradeTrialModal from '@/components/payment/UpgradeTrialModal';
import { TeamAnalysisNoticeBox } from '@/components/payment/TeamAnalysisNoticeModal';
import { getUpgradeContext } from '@/lib/api/activation';

/** 有效期至 YYYY-MM-DD（本地时区） */
function formatCouponDay(iso: string): string {
  const d = toDate(iso);
  if (!d) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

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

// ── 宽版方案选择视图子组件（UI 对齐设计稿 wiki/开发文档/10-05/newpay.html）──

type WidePlanId = 'free' | 'quarterly_package' | 'annual_package';

/** 套餐主题（free=绿 / quarterly=蓝 / annual=紫，取自设计稿色板） */
const WIDE_PLAN_THEME: Record<
  WidePlanId,
  { deep: string; soft: string; border: string; mark: string; selectedShadow: string }
> = {
  free: {
    deep: 'text-[#176a57]',
    soft: 'bg-[#edf9f5]',
    border: 'border-[#176a57]',
    mark: 'border-[#147b65] bg-[#147b65]',
    selectedShadow: 'shadow-[0_0_0_2px_rgba(20,123,101,0.17),0_14px_30px_rgba(31,48,64,0.08)]',
  },
  quarterly_package: {
    deep: 'text-[#254f9d]',
    soft: 'bg-[#eef4ff]',
    border: 'border-[#254f9d]',
    mark: 'border-[#3569d4] bg-[#3569d4]',
    selectedShadow: 'shadow-[0_0_0_2px_rgba(53,105,212,0.17),0_14px_30px_rgba(31,48,64,0.08)]',
  },
  annual_package: {
    deep: 'text-[#51399f]',
    soft: 'bg-[#f3f0ff]',
    border: 'border-[#51399f]',
    mark: 'border-[#6f52c7] bg-[#6f52c7]',
    selectedShadow: 'shadow-[0_0_0_2px_rgba(111,82,199,0.17),0_14px_30px_rgba(31,48,64,0.08)]',
  },
};

/** 方案卡：编号 + 名称/定位 + 推荐标 + 一句话承诺 + ✓ 特性列表（付费卡可点选，免费卡仅展示） */
function WidePlanCard({
  plan,
  index,
  name,
  role,
  promise,
  features,
  recommend,
  selected,
  selectedTag,
  selectable,
  onSelect,
}: {
  plan: WidePlanId;
  index: string;
  name: string;
  role: string;
  promise: string;
  features: string[];
  recommend?: string;
  selected: boolean;
  selectedTag: string;
  selectable: boolean;
  onSelect: () => void;
}) {
  const theme = WIDE_PLAN_THEME[plan];
  return (
    <article
      role={selectable ? 'button' : undefined}
      tabIndex={selectable ? 0 : undefined}
      aria-pressed={selectable ? selected : undefined}
      aria-disabled={selectable ? undefined : true}
      aria-label={selectable ? `${name}` : undefined}
      onClick={selectable ? onSelect : undefined}
      onKeyDown={
        selectable
          ? (e) => {
              if (e.key !== 'Enter' && e.key !== ' ') return;
              e.preventDefault();
              onSelect();
            }
          : undefined
      }
      className={`relative flex min-h-[286px] w-full min-w-0 flex-col rounded-[19px] border bg-white/80 px-[19px] pb-[17px] pt-[19px] transition max-[860px]:min-h-0 ${
        selected
          ? `${theme.border} bg-white ${theme.selectedShadow}`
          : `border-[#e3e8ec] ${
              selectable
                ? 'cursor-pointer hover:-translate-y-0.5 hover:border-[#b7c0ca] hover:bg-white hover:shadow-[0_12px_28px_rgba(31,48,64,0.07)]'
                : 'cursor-default'
            }`
      } focus:outline-none focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-[3px] focus-visible:outline-[rgba(53,105,212,0.25)]`}
    >
      {selected && selectable && (
        <span
          className={`absolute right-[14px] top-[14px] rounded-full px-2 py-1 text-[10px] font-bold ${theme.soft} ${theme.deep}`}
        >
          {selectedTag}
        </span>
      )}
      <div className="mb-3 flex min-h-[52px] items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-[9px]">
          <span
            aria-hidden
            className={`grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[10px] text-[11px] font-extrabold tracking-[0.04em] ${theme.soft} ${theme.deep}`}
          >
            {index}
          </span>
          <span className="min-w-0">
            <span className="block text-xl font-bold leading-[1.2] tracking-[-0.025em] text-[#182130]">
              {name}
            </span>
            <span className="mt-[5px] block text-xs leading-[1.4] text-[#5f6c7d]">{role}</span>
          </span>
        </div>
      </div>
      {recommend && (
        <span className="mb-2.5 inline-flex min-h-6 w-fit items-center rounded-full bg-[#eef4ff] px-[9px] text-[11px] font-bold text-[#254f9d]">
          {recommend}
        </span>
      )}
      <p className="mb-3 min-h-[44px] text-sm font-medium leading-[1.55] text-[#465366] max-[860px]:min-h-0">
        {promise}
      </p>
      <ul className="grid list-none gap-2 p-0">
        {features.map((f) => (
          <li key={f} className="relative min-h-5 pl-6 text-[13px] leading-[1.55] text-[#465366]">
            <span
              aria-hidden
              className={`absolute left-0 top-[2px] grid h-[17px] w-[17px] place-items-center rounded-full text-[11px] font-extrabold ${theme.soft} ${theme.deep}`}
            >
              ✓
            </span>
            {f}
          </li>
        ))}
      </ul>
    </article>
  );
}

/** 价格选择条：sr-only 单选 + 选择圈 + 名称/说明 + 价格（免费版为静态虚线框，见调用处内联实现） */
function WidePriceOption({
  plan,
  name,
  note,
  price,
  selected,
  ariaLabel,
  disabled,
  onSelect,
}: {
  plan: WidePlanId;
  name: string;
  note: string;
  price: string;
  selected: boolean;
  ariaLabel: string;
  disabled?: boolean;
  onSelect: () => void;
}) {
  const theme = WIDE_PLAN_THEME[plan];
  return (
    <label
      className={`relative flex min-h-[66px] min-w-0 items-center justify-between gap-3 rounded-[14px] border px-[13px] py-[11px] transition ${
        selected
          ? `${theme.border} ${theme.soft} shadow-[0_0_0_2px_rgba(53,105,212,0.12)]`
          : 'border-[#cbd3dc] bg-white hover:border-[#9ba8b5]'
      } ${disabled ? 'pointer-events-none opacity-70' : 'cursor-pointer'}`}
    >
      <input
        type="radio"
        name="purchase-plan"
        value={plan}
        className="sr-only"
        checked={selected}
        onChange={onSelect}
        aria-label={ariaLabel}
        disabled={disabled}
      />
      <span className="flex min-w-0 items-center gap-[9px]">
        <span
          aria-hidden
          className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border-[1.5px] text-[11px] font-extrabold ${
            selected ? `${theme.mark} text-white` : 'border-[#98a4af] bg-white text-transparent'
          }`}
        >
          ✓
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-[#293644]">{name}</span>
          <span className="mt-[3px] block text-[11px] leading-[1.35] text-[#5f6c7d]">{note}</span>
        </span>
      </span>
      <span className={`shrink-0 text-right ${theme.deep}`}>
        <strong className="block text-[22px] font-bold leading-[1.05] tracking-[-0.035em]">
          {price}
        </strong>
      </span>
    </label>
  );
}

/**
 * 二维码舞台：下单前为占位框（四角标 + 渠道标 + 标题），下单后为支付宝前置模式 iframe
 * （后端 qr_pay_mode=4 / qrcode_width=220，iframe 248×300 含支付宝页内边距，stage 随内容自适应）。
 */
function QrStage({
  active,
  payUrl,
  iframeTitle,
  placeholderTitle,
  hint,
}: {
  active: boolean;
  payUrl: string | null;
  iframeTitle: string;
  placeholderTitle: string;
  hint: string;
}) {
  return (
    <div
      aria-live="polite"
      className="relative mx-auto grid w-fit place-items-center rounded-2xl border border-[#c6cfd8] bg-white p-[7px] shadow-[0_8px_20px_rgba(31,48,64,0.07)]"
    >
      {active && payUrl ? (
        <iframe
          src={payUrl}
          title={iframeTitle}
          width={248}
          height={300}
          className="rounded-xl bg-white"
        />
      ) : (
        <div className="relative flex h-[160px] w-[160px] flex-col items-center justify-center rounded-[10px] border border-dashed border-[#aeb9c4] bg-[#f7f9fc] p-5 text-center">
          {/* 四角标（设计稿 .qr-corner） */}
          <i
            aria-hidden
            className="absolute left-[10px] top-[10px] h-[19px] w-[19px] border-l-[3px] border-t-[3px] border-[#8996a3]"
          />
          <i
            aria-hidden
            className="absolute right-[10px] top-[10px] h-[19px] w-[19px] border-r-[3px] border-t-[3px] border-[#8996a3]"
          />
          <i
            aria-hidden
            className="absolute bottom-[10px] left-[10px] h-[19px] w-[19px] border-b-[3px] border-l-[3px] border-[#8996a3]"
          />
          <i
            aria-hidden
            className="absolute bottom-[10px] right-[10px] h-[19px] w-[19px] border-b-[3px] border-r-[3px] border-[#8996a3]"
          />
          <span
            aria-hidden
            className="mb-2 grid h-[38px] w-[38px] place-items-center rounded-[11px] bg-[#1677ff] text-base font-extrabold text-white"
          >
            支
          </span>
          <strong className="text-[13px] font-semibold text-[#293644]">{placeholderTitle}</strong>
          <span className="sr-only">{hint}</span>
        </div>
      )}
    </div>
  );
}

/** 对比表单元格值：boolean=是否包含（✓ / —），string=文案 */
type WideCompareCell = string | boolean;

type WideCompareRow = {
  label: string;
  free: WideCompareCell;
  quarterly: WideCompareCell;
  annual: WideCompareCell;
};

/** 折叠式三列功能对比（免费 / 启程 / 同行），选中付费列高亮 */
function CompareSection({
  open,
  onToggle,
  rows,
  activeType,
  freeName,
  quarterlyName,
  annualName,
  t,
}: {
  open: boolean;
  onToggle: () => void;
  rows: WideCompareRow[];
  activeType: ProductType;
  freeName: string;
  quarterlyName: string;
  annualName: string;
  t: (k: string) => string;
}) {
  const cols: Array<{
    key: WidePlanId;
    rowKey: 'free' | 'quarterly' | 'annual';
    name: string;
    active: boolean;
  }> = [
    { key: 'free', rowKey: 'free', name: freeName, active: false },
    {
      key: 'quarterly_package',
      rowKey: 'quarterly',
      name: quarterlyName,
      active: activeType === 'quarterly_package',
    },
    {
      key: 'annual_package',
      rowKey: 'annual',
      name: annualName,
      active: activeType === 'annual_package',
    },
  ];
  return (
    <div className="mt-3.5 overflow-hidden rounded-2xl border border-[#e3e8ec] bg-white/70">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex min-h-[50px] w-full items-center justify-between gap-4 px-[17px]"
      >
        <span className="text-sm font-semibold text-[#293644]">
          {t('payment.dialog.compareTitle')}
        </span>
        <span className="flex items-center gap-2 text-xs text-[#5f6c7d]">
          {open ? t('payment.dialog.compareCollapse') : t('payment.dialog.compareExpand')}
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
            aria-hidden
          />
        </span>
      </button>
      {open && (
        <div
          className="overflow-x-auto px-3.5 pb-3.5"
          role="region"
          aria-label={t('payment.dialog.compareTitle')}
          tabIndex={0}
        >
          <table className="w-full min-w-[720px] border-separate border-spacing-0 text-xs leading-[1.55] text-[#465366]">
            <thead>
              <tr>
                <th
                  scope="col"
                  className="w-1/4 border-b border-[#e3e8ec] bg-[#f7f9fc] px-3 py-2 text-left font-semibold text-[#293644]"
                >
                  {t('payment.compare.colFeature')}
                </th>
                {cols.map((col) => (
                  <th
                    key={col.key}
                    scope="col"
                    className={`w-1/4 border-b border-[#e3e8ec] px-3 py-2 text-center font-semibold ${
                      col.active ? 'bg-[#eef4ff] text-[#254f9d]' : 'bg-[#f7f9fc] text-[#293644]'
                    }`}
                  >
                    {col.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th
                    scope="row"
                    className="border-b border-[#e3e8ec] px-3 py-2 text-left font-normal"
                  >
                    {row.label}
                  </th>
                  {cols.map((col) => {
                    const v = row[col.rowKey];
                    return (
                      <td
                        key={col.key}
                        className={`border-b border-[#e3e8ec] px-3 py-2 text-center ${
                          col.active ? 'bg-[#eef4ff]/60 text-[#254f9d]' : ''
                        }`}
                      >
                        {typeof v === 'boolean' ? (
                          v ? (
                            <Check
                              className="mx-auto h-[15px] w-[15px] text-[#147b65]"
                              strokeWidth={2.5}
                              aria-label={t('payment.compare.included')}
                            />
                          ) : (
                            '—'
                          )
                        ) : (
                          v
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2.5 text-xs leading-[1.65] text-[#5f6c7d]">
            {t('payment.dialog.compareFootnote')}
          </p>
        </div>
      )}
    </div>
  );
}

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
  const [appliedCoupon, setAppliedCoupon] = useState<{
    code: string;
    amount: number;
    expires_at: string | null;
  } | null>(null);
  const [couponError, setCouponError] = useState<string | null>(null);
  const [couponChecking, setCouponChecking] = useState(false);
  /** 我的可用券（打开弹窗时懒加载一次；接口失败静默降级为只显示输入框） */
  const [myCoupons, setMyCoupons] = useState<MyCouponItem[]>([]);
  const [order, setOrder] = useState<OrderItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  /** 等待支付视图：支付串（qr=iframe 嵌入二维码；redirect=收银台跳转 URL，「点击重开」用） */
  const [payUrl, setPayUrl] = useState<string | null>(null);
  const [payType, setPayType] = useState<PayType>('redirect');
  const [waitStatus, setWaitStatus] = useState<WaitStatus>('polling');
  /** 消耗升级弹窗（ADR-0014）：套餐成功交付且有已开聊试用码时弹出 */
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  /** 宽版方案选择视图：功能对比折叠区 */
  const [compareOpen, setCompareOpen] = useState(false);
  /** 消耗升级完成（本弹窗内或后端直购自动升级）：成功视图切换为「已升级」态 */
  const [trialUpgraded, setTrialUpgraded] = useState(false);
  /** 弹窗消耗升级实际用掉的付费码（从展示列表排除） */
  const [consumedCode, setConsumedCode] = useState<string | null>(null);

  const successFiredRef = useRef(false);
  /** 宽模式结算面板（startWaiting 后滚入视野） */
  const paymentPanelRef = useRef<HTMLDivElement>(null);

  const selectedProduct =
    products.find((p) => p.product_type === selectedType) ?? products[0] ?? FALLBACK_PRODUCTS[0];
  /** 咨询模式单独定价：优先接口价，兜底 ¥298 */
  const consultationProduct =
    products.find((p) => p.product_type === 'consultation') ?? FALLBACK_PRODUCTS[2];
  const priceProduct = consultationMode ? consultationProduct : selectedProduct;
  // 延期模式价格由后端按码类型定价，前端下单前不展示确定金额
  const finalAmount = Math.max(0, priceProduct.price - (appliedCoupon?.amount ?? 0));

  /** 套餐名称（i18n 缺失时回退接口名） */
  const planName = (p: ProductItem): string => {
    const key = `payment.plan.${p.product_type}.name`;
    const val = t(key);
    return val === key ? p.name : val;
  };

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
    setPayType('redirect');
    setWaitStatus('polling');
    setUpgradeOpen(false);
    setTrialUpgraded(false);
    setCompareOpen(false);
    successFiredRef.current = false;
  }, []);

  // ── 进入等待支付视图：qr 在本页 iframe 内嵌二维码；redirect 新标签页打开收银台 ──
  const startWaiting = useCallback((ord: OrderItem, url: string, type: PayType = 'redirect') => {
    setOrder(ord);
    setPayUrl(url);
    setPayType(type);
    setWaitStatus('polling');
    setView('waiting');
    if (type === 'redirect') window.open(url, '_blank');
    // 宽模式：结算面板滚入视野，保证二维码立即可见（窄模式无该节点，静默跳过）
    requestAnimationFrame(() =>
      paymentPanelRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }),
    );
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

    // 懒加载「我的可用券」：失败静默，只显示手动输入框
    setMyCoupons([]);
    listMyCoupons()
      .then((res) => setMyCoupons(res.available))
      .catch(() => {
        /* 静默降级 */
      });

    if (resumeOrderId) {
      getOrder(resumeOrderId)
        .then((res) => {
          const st = res.order.status;
          if ((st === 'pending' || st === 'paid') && res.pay_url) {
            // 继续支付：qr 在本页 iframe 嵌入二维码，redirect 新标签页打开收银台
            startWaiting(res.order, res.pay_url, res.pay_type ?? 'redirect');
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
  const handleApplyCoupon = async (codeOverride?: string) => {
    const code = normalizeCouponCode(codeOverride ?? couponInput);
    if (!code || couponChecking) return;
    setCouponChecking(true);
    setCouponError(null);
    try {
      const res = await validateCoupon(code);
      setAppliedCoupon({ code: res.code, amount: res.amount, expires_at: res.expires_at ?? null });
    } catch (e: unknown) {
      setAppliedCoupon(null);
      setCouponError(getApiErrorMessage(e, t('payment.coupon.invalid')));
    } finally {
      setCouponChecking(false);
    }
  };

  /** 选中「我的可用券」下拉项：填入券码并自动触发校验 */
  const handleSelectMyCoupon = (code: string) => {
    if (!code) return;
    setCouponInput(code);
    void handleApplyCoupon(code);
  };

  /** 「我的可用券」下拉（仅在拉取到可用券时渲染） */
  const renderMyCouponsSelect = (selectClassName: string) =>
    myCoupons.length === 0 ? null : (
      <select
        value=""
        onChange={(e) => handleSelectMyCoupon(e.target.value)}
        aria-label={t('payment.coupon.myCoupons')}
        className={selectClassName}
      >
        <option value="" disabled>
          {t('payment.coupon.myCouponsPlaceholder')}
        </option>
        {myCoupons.map((c) => (
          <option key={c.code} value={c.code}>
            ¥{fenToYuan(c.amount)} · {c.code}
            {c.expires_at
              ? ` · ${t('payment.coupon.expiresAt', { date: formatCouponDay(c.expires_at) })}`
              : ''}
          </option>
        ))}
      </select>
    );

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
        // qr：本页 iframe 嵌入二维码；redirect：新标签页打开收银台（本页轮询等待支付完成）
        startWaiting(res.order, res.payment.pay_url, res.payment.pay_type ?? 'redirect');
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
  /** 宽版方案选择视图（套餐下单与等待支付；延期/咨询下单及成功视图保持窄弹窗），UI 对齐设计稿 wiki/开发文档/10-05/newpay.html */
  const wideMode = !renewalMode && !consultationMode && view !== 'success';
  const quarterlyProduct =
    products.find((p) => p.product_type === 'quarterly_package') ?? FALLBACK_PRODUCTS[0];
  const annualProduct =
    products.find((p) => p.product_type === 'annual_package') ?? FALLBACK_PRODUCTS[1];
  /** 宽模式等待支付子态：金额与套餐以服务端订单为准（resume 单可能是另一套餐） */
  const wideWaiting = wideMode && view === 'waiting' && order !== null;
  const displayType: ProductType = wideWaiting && order ? order.product_type : selectedType;
  const displayProduct =
    products.find((p) => p.product_type === displayType) ?? selectedProduct;
  const displayAmount = wideWaiting && order ? order.amount_paid : finalAmount;
  /** 二维码激活：等待轮询中且为 qr 类型（支付宝前置模式 iframe） */
  const qrActive = wideWaiting && waitStatus === 'polling' && payType === 'qr' && !!payUrl;

  /** 三列功能对比行（boolean=是否包含；string=文案），免费列取自设计稿静态信息 */
  const wideCompareRows: WideCompareRow[] = [
    {
      label: t('payment.compare.quota'),
      free: t('payment.compare.quotaFree'),
      quarterly: t('payment.compare.quotaValue'),
      annual: t('payment.compare.quotaValue'),
    },
    {
      label: t('payment.compare.phases'),
      free: t('payment.compare.phasesFree'),
      quarterly: t('payment.compare.phasesValue'),
      annual: t('payment.compare.phasesValue'),
    },
    {
      label: t('payment.compare.reports'),
      free: false,
      quarterly: t('payment.compare.reportsQuarterly'),
      annual: t('payment.compare.reportsAnnual'),
    },
    { label: t('payment.compare.review'), free: false, quarterly: true, annual: true },
    {
      label: t('payment.compare.recheck'),
      free: false,
      quarterly: t('payment.compare.recheckValue'),
      annual: t('payment.compare.recheckValue'),
    },
    {
      label: t('payment.compare.codes'),
      free: t('payment.compare.codesFree'),
      quarterly: t('payment.compare.codesQuarterly'),
      annual: t('payment.compare.codesAnnual'),
    },
    { label: t('payment.compare.team'), free: false, quarterly: false, annual: true },
    {
      label: t('payment.compare.scene'),
      free: t('payment.compare.sceneFree'),
      quarterly: t('payment.compare.sceneQuarterly'),
      annual: t('payment.compare.sceneAnnual'),
    },
  ];

  /** 金额行主按钮：下单视图=生成付款码；等待轮询=禁用；已关闭/过期=重新下单 */
  const amountButtonLabel = wideWaiting
    ? waitStatus === 'polling'
      ? t('payment.wide.waitingPay')
      : t('payment.waiting.reorder')
    : submitting
      ? t('payment.creating')
      : displayAmount <= 0
        ? t('payment.payFree')
        : t('payment.wide.generateQr');
  const handleAmountButtonClick = () => {
    if (wideWaiting) {
      if (waitStatus !== 'polling') resetToOrderView();
      return;
    }
    void handlePay();
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
            className={`absolute inset-0 ${wideMode ? 'bg-[#182130]/58 backdrop-blur-[12px]' : 'bg-stone-900/25 backdrop-blur-[2px]'}`}
            aria-label="关闭"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal
            aria-labelledby="purchase-modal-title"
            className={
              wideMode
                ? 'relative flex max-h-[calc(100dvh-40px)] w-full max-w-[1240px] flex-col overflow-hidden rounded-[26px] border border-white/95 bg-[#fbfcfb] shadow-[0_16px_40px_rgba(24,33,48,0.16)]'
                : 'relative w-full max-w-md max-h-[85vh] flex flex-col rounded-2xl border border-stone-200/80 bg-white/95 shadow-[0_24px_80px_-24px_rgba(15,23,42,0.18),0_0_0_1px_rgba(255,255,255,0.6)_inset]'
            }
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.32, ease: [0.25, 0.8, 0.35, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            {wideMode ? (
              <>
                {/* 右上角浮动关闭（对齐设计稿 10-05/newpay.html） */}
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="关闭"
                  className="absolute right-[22px] top-5 z-10 grid h-[42px] w-[42px] place-items-center rounded-full text-[29px] font-light leading-none text-[#5f6c7d] transition hover:bg-[#eef2f5] hover:text-[#182130] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3569d4]/40 max-[700px]:right-3 max-[700px]:top-3"
                >
                  ×
                </button>

                <div className="overflow-y-auto overscroll-contain">
                  {/* 弹窗头：eyebrow + 主标题 */}
                  <header className="border-b border-[#e3e8ec]/85 bg-white/70 px-[38px] pb-5 pt-[30px] max-[1080px]:px-[26px] max-[700px]:px-5 max-[700px]:pb-[17px] max-[700px]:pt-6">
                    <div className="mb-2 flex items-center gap-2.5 text-xs font-bold tracking-[0.08em] text-[#254f9d]">
                      <span
                        aria-hidden
                        className="h-[7px] w-[7px] rounded-full bg-[#3569d4] shadow-[0_0_0_5px_rgba(53,105,212,0.1)]"
                      />
                      {t('payment.wide.eyebrow')}
                    </div>
                    <h1
                      id="purchase-modal-title"
                      className="text-[clamp(25px,2.4vw,34px)] font-bold leading-[1.2] tracking-[-0.045em] text-[#182130]"
                    >
                      {t('payment.wide.title')}
                    </h1>
                  </header>

                  <main className="px-[38px] pb-6 pt-[22px] max-[1080px]:px-[26px] max-[700px]:px-4">
                    {/* 选择探索版本：三列方案卡（免费版仅展示）+ 价格选择条 */}
                    <section aria-label={t('payment.wide.sectionTitle')}>
                      <div className="mb-3 flex items-center justify-between gap-4">
                        <strong className="text-[15px] font-bold text-[#293644]">
                          {t('payment.wide.sectionTitle')}
                        </strong>
                      </div>
                      <div
                        aria-disabled={wideWaiting}
                        className={`grid grid-cols-3 gap-3.5 max-[860px]:grid-cols-1 ${
                          wideWaiting ? 'pointer-events-none opacity-70' : ''
                        }`}
                      >
                        {/* 免费版：仅展示不可选（试用流程不在本弹窗） */}
                        <div className="flex min-w-0 flex-col gap-2.5">
                          <WidePlanCard
                            plan="free"
                            index="01"
                            name={t('payment.wide.free.name')}
                            role={t('payment.wide.free.role')}
                            promise={t('payment.wide.free.promise')}
                            features={[
                              t('payment.wide.free.f1'),
                              t('payment.wide.free.f2'),
                              t('payment.wide.free.f3'),
                              t('payment.wide.free.f4'),
                            ]}
                            selected={false}
                            selectedTag={t('payment.wide.selectedTag')}
                            selectable={false}
                            onSelect={() => {}}
                          />
                          {/* 免费版价格条（静态，无单选） */}
                          <div className="flex min-h-[66px] min-w-0 items-center justify-between gap-3 rounded-[14px] border border-dashed border-[#b9c5c0] bg-[#f4f8f6] px-[13px] py-[11px] opacity-90">
                            <span className="min-w-0">
                              <span className="block text-sm font-semibold text-[#293644]">
                                {t('payment.wide.free.name')}
                              </span>
                              <span className="mt-[3px] block text-[11px] leading-[1.35] text-[#5f6c7d]">
                                {t('payment.wide.free.priceNote')}
                              </span>
                            </span>
                            <span className="inline-flex min-h-[25px] shrink-0 items-center whitespace-nowrap rounded-full bg-[#edf9f5] px-2.5 text-[11px] font-semibold text-[#176a57]">
                              {t('payment.wide.freeBadge')}
                            </span>
                          </div>
                        </div>

                        {/* 启程版（quarterly_package） */}
                        <div className="flex min-w-0 flex-col gap-2.5">
                          <WidePlanCard
                            plan="quarterly_package"
                            index="02"
                            name={planName(quarterlyProduct)}
                            role={t('payment.wide.quarterly.role')}
                            promise={t('payment.wide.quarterly.promise')}
                            features={[
                              t('payment.plan.quarterly_package.f1'),
                              t('payment.plan.quarterly_package.f2'),
                              t('payment.plan.quarterly_package.f3'),
                              t('payment.plan.quarterly_package.f4'),
                            ]}
                            recommend={
                              quarterlyProduct.popular ? t('payment.plan.popular') : undefined
                            }
                            selected={displayType === 'quarterly_package'}
                            selectedTag={t('payment.wide.selectedTag')}
                            selectable
                            onSelect={() => setSelectedType('quarterly_package')}
                          />
                          <WidePriceOption
                            plan="quarterly_package"
                            name={t('payment.wide.quarterly.priceName')}
                            note={t('payment.wide.quarterly.priceNote')}
                            price={`¥${fenToYuan(quarterlyProduct.price)}`}
                            selected={displayType === 'quarterly_package'}
                            ariaLabel={`${planName(quarterlyProduct)}，¥${fenToYuan(quarterlyProduct.price)}，${t('payment.wide.quarterly.priceNote')}`}
                            disabled={wideWaiting}
                            onSelect={() => setSelectedType('quarterly_package')}
                          />
                        </div>

                        {/* 同行版（annual_package） */}
                        <div className="flex min-w-0 flex-col gap-2.5">
                          <WidePlanCard
                            plan="annual_package"
                            index="03"
                            name={planName(annualProduct)}
                            role={t('payment.wide.annual.role')}
                            promise={t('payment.wide.annual.promise')}
                            features={[
                              t('payment.plan.annual_package.f1'),
                              t('payment.plan.annual_package.f2'),
                              t('payment.plan.annual_package.f3'),
                              t('payment.plan.annual_package.f4'),
                            ]}
                            selected={displayType === 'annual_package'}
                            selectedTag={t('payment.wide.selectedTag')}
                            selectable
                            onSelect={() => setSelectedType('annual_package')}
                          />
                          <WidePriceOption
                            plan="annual_package"
                            name={t('payment.wide.annual.priceName')}
                            note={t('payment.wide.annual.priceNote')}
                            price={`¥${fenToYuan(annualProduct.price)}`}
                            selected={displayType === 'annual_package'}
                            ariaLabel={`${planName(annualProduct)}，¥${fenToYuan(annualProduct.price)}，${t('payment.wide.annual.priceNote')}`}
                            disabled={wideWaiting}
                            onSelect={() => setSelectedType('annual_package')}
                          />
                        </div>
                      </div>
                    </section>

                    {/* 折叠式三列功能对比（选中套餐列高亮） */}
                    <CompareSection
                      open={compareOpen}
                      onToggle={() => setCompareOpen((v) => !v)}
                      rows={wideCompareRows}
                      activeType={displayType}
                      freeName={t('payment.wide.free.name')}
                      quarterlyName={`${planName(quarterlyProduct)} · ¥${fenToYuan(quarterlyProduct.price)}`}
                      annualName={`${planName(annualProduct)} · ¥${fenToYuan(annualProduct.price)}`}
                      t={t}
                    />

                    {/* 结算面板：左二维码 + 右三行（金额 / 优惠码 / 支付方式）；下单后二维码在此渲染 */}
                    <section
                      ref={paymentPanelRef}
                      aria-label={t('payment.wide.generateQr')}
                      className="mt-3.5 overflow-hidden rounded-[18px] border border-[#e3e8ec] bg-white/95 shadow-[0_12px_30px_rgba(31,48,64,0.05)]"
                    >
                      <div className="grid grid-cols-1 min-[701px]:grid-cols-[296px_minmax(0,1fr)]">
                        {/* 二维码列：占位框 → 支付宝前置模式 iframe（生成付款码后） */}
                        <div className="grid place-items-center border-b border-[#e3e8ec] bg-[#fcfdfd] p-3.5 min-[701px]:border-b-0 min-[701px]:border-r">
                          <QrStage
                            active={qrActive}
                            payUrl={payUrl}
                            iframeTitle={t('payment.waiting.title')}
                            placeholderTitle={t('payment.wide.qrPlaceholderTitle')}
                            hint={t('payment.wide.qrHint')}
                          />
                        </div>

                        {/* 结算列：应付金额 / 优惠码 / 支付方式 */}
                        <div className="grid min-w-0 divide-y divide-[#e3e8ec]">
                          {/* 应付金额行：套餐 + 合计 + 生成付款码（等待支付时复用为状态按钮） */}
                          <div className="grid min-h-[68px] grid-cols-[76px_minmax(90px,1fr)_auto_auto] items-center gap-3 px-3.5 py-2.5 max-[700px]:grid-cols-[1fr_auto]">
                            <span className="text-[11px] font-bold tracking-[0.06em] text-[#5f6c7d] max-[700px]:col-span-2">
                              {t('payment.wide.amountLabel')}
                            </span>
                            <span className="min-w-0 truncate text-sm font-semibold text-[#293644]">
                              {planName(displayProduct)}
                              {appliedCoupon && !wideWaiting && (
                                <s className="ml-2 font-normal text-[#5f6c7d]">
                                  ¥{fenToYuan(priceProduct.price)}
                                </s>
                              )}
                            </span>
                            <strong className="whitespace-nowrap text-xl font-bold leading-none text-[#293644]">
                              ¥{fenToYuan(displayAmount)}
                            </strong>
                            <button
                              type="button"
                              onClick={handleAmountButtonClick}
                              disabled={submitting || (wideWaiting && waitStatus === 'polling')}
                              className="min-h-[38px] shrink-0 rounded-[10px] bg-[#222b35] px-[15px] text-xs font-semibold text-white transition hover:bg-[#151c23] hover:shadow-[0_10px_24px_rgba(24,33,48,0.15)] disabled:cursor-wait disabled:opacity-55 disabled:hover:shadow-none max-[700px]:col-span-2 max-[700px]:w-full"
                            >
                              {amountButtonLabel}
                            </button>
                          </div>

                          {/* 优惠码行：我的可用券 + 手动输入 + 使用（反馈走状态行） */}
                          <div className="grid min-h-[68px] grid-cols-[76px_minmax(0,1fr)] items-center gap-3 px-3.5 py-2.5 max-[700px]:grid-cols-1 max-[700px]:gap-2 max-[700px]:py-3">
                            <span className="text-[11px] font-bold tracking-[0.06em] text-[#5f6c7d]">
                              {t('payment.wide.couponLabel')}
                            </span>
                            <fieldset disabled={wideWaiting} className="min-w-0">
                              <div className="grid grid-cols-[minmax(116px,0.7fr)_minmax(150px,1fr)_auto] gap-1.5 max-[700px]:grid-cols-[1fr_auto]">
                                {renderMyCouponsSelect(
                                  'h-[42px] w-full min-w-0 rounded-[11px] border border-[#b6c0ca] bg-white px-2.5 text-xs text-[#293644] outline-none transition focus:border-[#3569d4] max-[700px]:col-span-2',
                                )}
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
                                  aria-label={t('payment.wide.couponLabel')}
                                  className="h-[42px] w-full min-w-0 rounded-[11px] border border-[#b6c0ca] bg-white px-3 text-xs text-[#293644] outline-none transition focus:border-[#3569d4]"
                                />
                                <button
                                  type="button"
                                  onClick={() => void handleApplyCoupon()}
                                  disabled={couponChecking || !couponInput.trim()}
                                  className="h-[42px] shrink-0 rounded-[11px] border border-[#aab5c0] bg-white px-3.5 text-xs font-semibold text-[#293644] transition hover:bg-[#f7f9fc] disabled:opacity-40"
                                >
                                  {couponChecking
                                    ? t('payment.coupon.checking')
                                    : t('payment.coupon.apply')}
                                </button>
                              </div>
                            </fieldset>
                          </div>

                          {/* 支付方式行：支付宝（微信即将上线，保持现有禁用态） */}
                          <div className="grid min-h-[68px] grid-cols-[76px_minmax(0,1fr)] items-center gap-3 px-3.5 py-2.5 max-[700px]:grid-cols-1 max-[700px]:gap-2 max-[700px]:py-3">
                            <span className="text-[11px] font-bold tracking-[0.06em] text-[#5f6c7d]">
                              {t('payment.channelLabel')}
                            </span>
                            <div className="grid max-w-[420px] grid-cols-2 gap-2">
                              <button
                                type="button"
                                onClick={() => setChannel('alipay')}
                                disabled={wideWaiting}
                                className={`flex min-h-[42px] items-center justify-center gap-[7px] rounded-xl border px-3 text-[13px] font-semibold transition ${
                                  channel === 'alipay'
                                    ? 'border-[#254f9d] bg-[#eef4ff] text-[#254f9d] shadow-[0_0_0_1px_rgba(37,79,157,0.13)]'
                                    : 'border-[#e3e8ec] bg-white text-[#465366] hover:border-[#aeb8c3]'
                                }`}
                              >
                                <span
                                  aria-hidden
                                  className="grid h-[23px] w-[23px] place-items-center rounded-[7px] bg-[#1677ff] text-[11px] font-extrabold text-white"
                                >
                                  支
                                </span>
                                {t('payment.channel.alipay')}
                              </button>
                              <button
                                type="button"
                                disabled
                                title={t('payment.channel.comingSoon')}
                                className="relative flex min-h-[42px] cursor-not-allowed items-center justify-center gap-[7px] rounded-xl border border-[#e3e8ec] bg-white/60 px-3 text-[13px] font-semibold text-[#9aa8bb]"
                              >
                                <span
                                  aria-hidden
                                  className="grid h-[23px] w-[23px] place-items-center rounded-[7px] bg-[#07c160] text-[11px] font-extrabold text-white"
                                >
                                  微
                                </span>
                                {t('payment.channel.wechat')}
                                <span className="absolute -top-2 right-2 rounded-full bg-stone-200 px-1.5 py-0.5 text-[10px] text-stone-500">
                                  {t('payment.channel.comingSoon')}
                                </span>
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    </section>

                    {/* 状态行：错误 / 等待支付（订单号 + 重开 + 取消）/ 券码反馈 */}
                    <p
                      role="status"
                      aria-live="polite"
                      className="mx-0.5 mt-2.5 min-h-5 text-xs leading-[1.6] text-[#5f6c7d]"
                    >
                      {error ? (
                        <span className="text-[#a63e4b]">{error}</span>
                      ) : couponError ? (
                        <span className="text-[#a63e4b]">{couponError}</span>
                      ) : wideWaiting ? (
                        waitStatus === 'polling' ? (
                          <>
                            <span className="text-[#147b65]">
                              {t('payment.wide.orderCreated', { no: order?.order_no ?? '' })} ·{' '}
                              {t('payment.wide.qrHint')}
                            </span>
                            {payUrl && (
                              <button
                                type="button"
                                onClick={() => payUrl && window.open(payUrl, '_blank')}
                                className="mx-1 text-[#3569d4] underline underline-offset-2"
                              >
                                {t('payment.waiting.reopen')}
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => void handleCancelOrder()}
                              className="mx-1 text-[#5f6c7d] underline underline-offset-2 transition hover:text-[#a63e4b]"
                            >
                              {t('payment.waiting.cancel')}
                            </button>
                          </>
                        ) : (
                          <span className="text-[#a63e4b]">
                            {waitStatus === 'expired'
                              ? t('payment.waiting.expired')
                              : t('payment.waiting.closed')}
                          </span>
                        )
                      ) : appliedCoupon ? (
                        <span className="text-[#147b65]">
                          {t('payment.coupon.applied', {
                            amount: fenToYuan(appliedCoupon.amount),
                          })}
                          {appliedCoupon.expires_at &&
                            ` · ${t('payment.coupon.expiresAt', { date: formatCouponDay(appliedCoupon.expires_at) })}`}
                        </span>
                      ) : null}
                    </p>

                    {/* 信任行 */}
                    <div className="mt-2 flex items-center justify-center gap-2 text-[11px] leading-[1.5] text-[#5f6c7d] max-[700px]:items-start max-[700px]:justify-start">
                      <span
                        aria-hidden
                        className="h-[5px] w-[5px] shrink-0 rounded-full bg-[#147b65]"
                      />
                      {t('payment.wide.trust')}
                    </div>
                  </main>
                </div>

              </>
            ) : (
              <>
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
                  ) : null}

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
                    {renderMyCouponsSelect(
                      'w-full rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 text-sm text-stone-800 outline-none transition focus:border-stone-400',
                    )}
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
                        {appliedCoupon.expires_at &&
                          ` · ${t('payment.coupon.expiresAt', { date: formatCouponDay(appliedCoupon.expires_at) })}`}
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
                /* 等待支付：qr 在本页 iframe 嵌入二维码（支付宝前置模式），本页轮询订单状态 */
                <div className="space-y-5">
                  {waitStatus === 'polling' ? (
                    <div className="flex flex-col items-center space-y-3 py-4 text-center">
                      {payType === 'qr' && payUrl ? (
                        /* 支付宝前置模式：iframe 内只渲染二维码（qrcode_width=220，含支付宝页内边距） */
                        <iframe
                          src={payUrl}
                          title={t('payment.waiting.title')}
                          width={248}
                          height={300}
                          className="rounded-xl border border-stone-200 bg-white"
                        />
                      ) : (
                        <Loader2 className="h-8 w-8 animate-spin text-stone-400" />
                      )}
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
              </>
            )}
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
