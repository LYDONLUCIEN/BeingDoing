'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Check, Copy, Gift, Ticket } from 'lucide-react';
import { apiClient, getApiErrorMessage, isRequestCanceled } from '@/lib/api/client';
import { listMyCodes, type CodeType, type MyCodeItem } from '@/lib/api/activation';
import { setLastActivationCode } from '@/lib/explore/session';
import { fetchMyPurchasedCodes, type PurchasedCodeItem } from '@/lib/api/teamAnalysis';
import { formatLocalDateTime, toDate } from '@/lib/utils/formatTime';
import PurchaseModal from '@/components/payment/PurchaseModal';
import UpgradeTrialModal from '@/components/payment/UpgradeTrialModal';
import FreeRenewalClaimModal from '@/components/payment/FreeRenewalClaimModal';
import OrdersSection from '@/components/dashboard/OrdersSection';
import CouponsSection from '@/components/dashboard/CouponsSection';
import { useLocale } from '@/hooks/useLocale';
import DashboardPageHeader from '@/components/dashboard/DashboardPageHeader';

type CodesTab = 'codes' | 'orders' | 'coupons';

/** 状态 badge 配色：active 绿 / inactive 橙 / expired 灰 / revoked 红 / consumed 灰 / 其他 灰 */
const STATUS_COLOR: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  inactive: 'bg-orange-100 text-orange-700 border-orange-200',
  expired: 'bg-neutral-200 text-neutral-600 border-neutral-300',
  revoked: 'bg-red-100 text-red-700 border-red-200',
  consumed: 'bg-neutral-200 text-neutral-600 border-neutral-300',
};

/** 类型 badge 配色：trial 蓝 / full 金 */
const TYPE_COLOR: Record<CodeType, string> = {
  trial: 'bg-sky-100 text-sky-700 border-sky-200',
  full: 'bg-amber-100 text-amber-700 border-amber-200',
};

function CodeCard({
  item,
  copied,
  onCopy,
  onUse,
  onRenew,
  onUpgrade,
  onClaimFree,
  t,
}: {
  item: MyCodeItem;
  copied: boolean;
  onCopy: (text: string) => void;
  onUse: (code: string) => void;
  onRenew: (code: string) => void;
  onUpgrade: () => void;
  onClaimFree: (code: string) => void;
  t: (k: string, params?: Record<string, string>) => string;
}) {
  // 「付费升级」溯源：默认折叠，点击展开才显示来源付费码完整码值
  const [showSourceCode, setShowSourceCode] = useState(false);
  const codeType: CodeType = item.code_type === 'trial' ? 'trial' : 'full';
  const statusKey = `dashboard.codesPage.status.${item.status}`;
  const statusLabel = t(statusKey) === statusKey ? item.status : t(statusKey);
  const sourceKey = `dashboard.codesPage.source.${item.source ?? ''}`;
  const sourceLabel =
    item.source && t(sourceKey) !== sourceKey ? t(sourceKey) : (item.source ?? '—');

  const formatTime = (iso?: string | null) => {
    if (!iso) return '—';
    const formatted = formatLocalDateTime(iso);
    return formatted === '-' ? iso : formatted;
  };

  /** 完整码剩余天数（到期后不再显示） */
  const daysLeft = (() => {
    if (codeType === 'trial' || !item.expires_at) return null;
    const exp = toDate(item.expires_at);
    if (!exp) return null;
    const days = Math.ceil((exp.getTime() - Date.now()) / (24 * 60 * 60 * 1000));
    return days >= 0 ? days : null;
  })();

  return (
    <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-5">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="font-mono text-base font-semibold tracking-wider text-bd-fg">
          {item.code}
        </span>
        <button
          type="button"
          onClick={() => onCopy(item.code)}
          className="inline-flex items-center gap-1 rounded-lg border border-bd-border px-2 py-1 text-[11px] text-bd-muted transition hover:bg-bd-overlay-md hover:text-bd-fg"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-500" />
              {t('dashboard.codesPage.copied')}
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              {t('dashboard.codesPage.copy')}
            </>
          )}
        </button>
        <span
          className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${TYPE_COLOR[codeType]}`}
        >
          {t(`dashboard.codesPage.type.${codeType}`)}
        </span>
        <span
          className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
            STATUS_COLOR[item.status] ?? STATUS_COLOR.expired
          }`}
        >
          {statusLabel}
        </span>
        {item.upgraded_from_code && (
          <span className="rounded-full border px-2 py-0.5 text-[11px] font-medium bg-amber-500 text-white border-amber-500">
            {t('dashboard.codesPage.paidUpgradeBadge')}
          </span>
        )}
        {item.free_renewal_available && (
          <button
            type="button"
            onClick={() => onClaimFree(item.code)}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-700 transition hover:bg-emerald-50"
          >
            <Gift className="h-3 w-3" />
            {t('dashboard.codesPage.claimFreeRenewal')}
          </button>
        )}
        {codeType === 'full' && (
          <button
            type="button"
            onClick={() => onRenew(item.code)}
            className={`${item.free_renewal_available ? '' : 'ml-auto '}inline-flex items-center gap-1.5 rounded-lg border border-bd-border px-3 py-1.5 text-xs font-medium text-bd-muted transition hover:bg-bd-overlay-md hover:text-bd-fg`}
          >
            {t('dashboard.codesPage.renew')}
          </button>
        )}
        {codeType === 'trial' && item.status === 'active' && (
          <button
            type="button"
            onClick={onUpgrade}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-50"
          >
            {t('dashboard.codesPage.upgradeTrial')}
          </button>
        )}
        <button
          type="button"
          onClick={() => onUse(item.code)}
          className={`${codeType === 'full' ? '' : 'ml-auto '}inline-flex items-center gap-1.5 rounded-lg bg-bd-ui-accent px-3 py-1.5 text-xs font-medium text-bd-ui-accent-fg transition hover:opacity-90`}
        >
          {t('dashboard.codesPage.goUse')}
        </button>
      </div>

      {item.upgraded_from_code && (
        <div className="mb-3 text-xs">
          <button
            type="button"
            onClick={() => setShowSourceCode((v) => !v)}
            className="text-amber-700 transition hover:underline"
          >
            {showSourceCode
              ? t('dashboard.codesPage.hideSourceCode')
              : t('dashboard.codesPage.viewSourceCode')}
          </button>
          {showSourceCode && (
            <span className="ml-2 font-mono tracking-wider text-bd-fg">
              {item.upgraded_from_code}
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
        <div className="space-y-0.5">
          <p className="text-[10px] text-bd-muted">{t('dashboard.codesPage.expiresLabel')}</p>
          <p className="text-bd-fg">
            {/* inactive（已购买未开始探索）：有效期首次创建 session 才起算；trial 不过期仍显示「不限」 */}
            {item.status === 'inactive'
              ? t('dashboard.codesPage.startsOnUse')
              : codeType === 'trial' || !item.expires_at
                ? t('dashboard.codesPage.noExpiry')
                : formatTime(item.expires_at)}
          </p>
          {daysLeft != null && (
            <p className="text-[10px] text-bd-muted">
              {t('dashboard.codesPage.daysLeft', { days: String(daysLeft) })}
            </p>
          )}
        </div>
        <div className="space-y-0.5">
          <p className="text-[10px] text-bd-muted">{t('dashboard.codesPage.sourceLabel')}</p>
          <p className="text-bd-fg">{sourceLabel}</p>
        </div>
        <div className="space-y-0.5">
          <p className="text-[10px] text-bd-muted">{t('dashboard.codesPage.createdAt')}</p>
          <p className="text-bd-fg">{formatTime(item.created_at)}</p>
        </div>
        <div className="space-y-0.5">
          <p className="text-[10px] text-bd-muted">{t('dashboard.codesPage.reportLabel')}</p>
          <p className="text-bd-fg">
            {/* 三态：审核中 / 已生成（approved） / 未生成；has_report 兜底旧数据 */}
            {item.report_status === 'pending_review'
              ? t('dashboard.codesPage.reportReviewing')
              : item.report_status === 'approved' || (item.report_status == null && item.has_report)
                ? t('dashboard.codesPage.reportReady')
                : t('dashboard.codesPage.reportNone')}
          </p>
        </div>
      </div>
    </div>
  );
}

export default function DashboardCodesPage() {
  const { t } = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [codes, setCodes] = useState<MyCodeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedText, setCopiedText] = useState<string | null>(null);
  /** 激活码延期目标码：非 null 时打开 PurchaseModal 延期模式 */
  const [renewalTarget, setRenewalTarget] = useState<string | null>(null);
  /** 7 天免费续期领取目标码（ADR-0015）：非 null 时打开领取弹窗 */
  const [freeRenewalTarget, setFreeRenewalTarget] = useState<string | null>(null);
  /** 消耗升级弹窗（ADR-0014）：试用码卡片「升级完整版」入口 */
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  /** 购买记录区刷新信号：升级/延期后递增，触发 PurchasedCodesSection 重新拉取 */
  const [purchasedRefreshKey, setPurchasedRefreshKey] = useState(0);
  /** 页签：激活码 / 订单记录（?tab=orders 定位到订单 tab） */
  const [activeTab, setActiveTab] = useState<CodesTab>('codes');
  /** 购买激活码弹窗（页面标题右侧入口） */
  const [purchaseOpen, setPurchaseOpen] = useState(false);
  /** 页面内直接绑定新激活码（复用 /simple-auth/activate）。 */
  const [bindCode, setBindCode] = useState('');
  const [binding, setBinding] = useState(false);
  const [bindStatus, setBindStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const isUiPreview =
    process.env.NODE_ENV === 'development' && searchParams.get('ui_preview') === '1';

  const loadCodes = useCallback(async () => {
    setLoading(true);
    try {
      if (isUiPreview) {
        setCodes([
          {
            code: 'OPENLIFE-2026',
            code_type: 'full',
            status: 'active',
            expires_at: '2027-06-18T08:30:00Z',
            created_at: '2026-08-25T09:06:00Z',
            source: 'purchase',
            has_report: false,
            report_status: 'not_started',
          },
          {
            code: 'TRIAL-0919',
            code_type: 'trial',
            status: 'active',
            expires_at: null,
            created_at: '2026-09-19T09:06:00Z',
            source: 'trial_gift',
            has_report: false,
            report_status: 'not_started',
          },
        ]);
        setError(null);
        return;
      }
      const items = await listMyCodes();
      setCodes(items);
      setError(null);
    } catch (e: unknown) {
      // 页面刷新/导航导致的请求取消不是错误，静默忽略（保留已有数据）
      if (isRequestCanceled(e)) return;
      setError(getApiErrorMessage(e, t('dashboard.codesPage.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [isUiPreview, t]);

  useEffect(() => {
    void loadCodes();
  }, [loadCodes]);

  // ?tab=orders 定位到订单 tab（默认激活码 tab）
  useEffect(() => {
    if (searchParams.get('tab') === 'orders') setActiveTab('orders');
  }, [searchParams]);

  // 过期通知邮件/站内信链接入口（ADR-0015）：?free_renewal=<code> 自动弹领取窗
  useEffect(() => {
    const code = (searchParams.get('free_renewal') || '').trim().toUpperCase();
    if (!code || loading) return;
    if (codes.some((c) => c.code === code)) {
      setFreeRenewalTarget(code);
    }
    // 无论码是否命中都清掉 query，避免刷新后反复弹窗
    router.replace('/dashboard/codes');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, loading]);

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedText(text);
      setTimeout(() => setCopiedText(null), 1500);
    } catch {
      /* 复制失败静默 */
    }
  };

  const switchTab = (tab: CodesTab) => {
    setActiveTab(tab);
    router.replace(tab === 'orders' ? '/dashboard/codes?tab=orders' : '/dashboard/codes');
  };

  /** 去使用：写入「上次激活码」并跳激活页（code 由激活页从 query 预填） */
  const handleUse = (code: string) => {
    setLastActivationCode(code);
    router.push(`/explore/activate?code=${encodeURIComponent(code)}`);
  };

  const handleBindCode = async () => {
    const value = bindCode.trim().toUpperCase();
    if (!value || binding) return;
    setBinding(true);
    setBindStatus(null);
    try {
      const response = await apiClient.post('/simple-auth/activate', { code: value });
      const activatedCode = String(response.data?.activation_code || value);
      setLastActivationCode(activatedCode);
      setBindCode('');
      setBindStatus({ type: 'success', message: `激活码 ${activatedCode} 已绑定到当前账号。` });
      await loadCodes();
      setPurchasedRefreshKey((key) => key + 1);
    } catch (err: unknown) {
      if (!isRequestCanceled(err)) {
        setBindStatus({ type: 'error', message: getApiErrorMessage(err, '绑定失败，请检查激活码是否正确') });
      }
    } finally {
      setBinding(false);
    }
  };

  return (
    <div className="ol-profile-content ol-codes-page">
      <DashboardPageHeader
        kicker="ACTIVATION ARCHIVE"
        title={t('dashboard.myCodes')}
        description="在这里查看权益、订单与可转赠的激活码；你的对话内容始终只对你可见。"
        action={(
          <button type="button" onClick={() => setPurchaseOpen(true)} className="ol-profile-heading-button">
            {t('dashboard.ordersPage.buy')}
          </button>
        )}
      />

      {/* 页签：激活码 / 订单记录（样式与 AuthModal tab 一致） */}
      <div className="mb-6 flex bg-bd-overlay rounded-lg p-1 max-w-xs">
        {(['codes', 'orders', 'coupons'] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => switchTab(tab)}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab
                ? 'bg-bd-primary text-bd-primary-fg shadow-sm'
                : 'text-bd-muted hover:text-bd-fg'
            }`}
          >
            {t(`dashboard.codesPage.tabs.${tab}`)}
          </button>
        ))}
      </div>

      {activeTab === 'codes' ? (
        <>
          {loading ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-bd-muted">{t('common.loading')}</p>
        </div>
      ) : error ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-red-600/90 dark:text-red-400/90 mb-4">{error}</p>
          <button
            type="button"
            onClick={() => void loadCodes()}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : codes.length === 0 ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-12 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-bd-overlay-md">
            <Ticket className="h-6 w-6 text-bd-muted" />
          </div>
          <p className="text-bd-muted">{t('dashboard.codesPage.empty')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {codes.map((item) => (
            <CodeCard
              key={item.code}
              item={item}
              copied={copiedText === item.code}
              onCopy={(text) => void copyText(text)}
              onUse={handleUse}
              onRenew={(code) => setRenewalTarget(code)}
              onUpgrade={() => setUpgradeOpen(true)}
              onClaimFree={(code) => setFreeRenewalTarget(code)}
              t={t}
            />
          ))}
        </div>
      )}
          <section className="ol-profile-code-entry ol-profile-surface">
            <div>
              <p className="ol-profile-kicker">BIND A NEW CODE</p>
              <h3>绑定新的激活码</h3>
              <p>新激活码会与当前账号关联，可用于开启旅程或升级权益。</p>
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void handleBindCode();
              }}
            >
              <label htmlFor="dashboard-bind-code">激活码</label>
              <div>
                <input
                  id="dashboard-bind-code"
                  value={bindCode}
                  onChange={(event) => setBindCode(event.target.value.toUpperCase())}
                  autoComplete="off"
                  autoCapitalize="characters"
                  placeholder="例如：OPEN-LIFE-2026"
                />
                <button className="ol-profile-primary" type="submit" disabled={!bindCode.trim() || binding}>
                  {binding ? '绑定中…' : '立即激活'}
                </button>
              </div>
              <p className={bindStatus?.type === 'error' ? 'is-error' : 'is-success'} role="status">
                {bindStatus?.message || ''}
              </p>
            </form>
          </section>
          {/* 我购买的激活码：每码去向/使用情况（订单详情见「订单记录」tab） */}
          <PurchasedCodesSection
            t={t}
            copiedText={copiedText}
            onCopy={(text) => void copyText(text)}
            onUse={handleUse}
            refreshKey={purchasedRefreshKey}
            uiPreview={isUiPreview}
          />
        </>
      ) : activeTab === 'coupons' ? (
        // 折扣券 tab：可用 / 已使用 / 已过期 三组
        isUiPreview ? (
          <PreviewTabPlaceholder title="折扣券" description="预览模式不会请求账号数据；登录后会显示真实折扣券。" />
        ) : (
          <CouponsSection />
        )
      ) : (
        // 订单记录 tab：仅订单详情 + 本单交付的激活码列表（码的去向见「激活码」tab）
        isUiPreview ? (
          <PreviewTabPlaceholder title="订单记录" description="预览模式不会请求账号数据；登录后会显示真实订单。" />
        ) : (
          <OrdersSection />
        )
      )}

      {/* 购买激活码：标题右侧「购买激活码」按钮入口 */}
      <PurchaseModal open={purchaseOpen} onClose={() => setPurchaseOpen(false)} />

      {/* 激活码延期：关闭后刷新列表（有效期可能已追加） */}
      <PurchaseModal
        open={renewalTarget !== null}
        onClose={() => {
          setRenewalTarget(null);
          void loadCodes();
          setPurchasedRefreshKey((k) => k + 1);
        }}
        renewalTargetCode={renewalTarget ?? undefined}
      />

      {/* 7 天免费续期领取（ADR-0015）：链接入口/卡片按钮触发 */}
      <FreeRenewalClaimModal
        open={freeRenewalTarget !== null}
        code={freeRenewalTarget}
        onClose={() => setFreeRenewalTarget(null)}
        onClaimed={() => {
          void loadCodes();
          setPurchasedRefreshKey((k) => k + 1);
        }}
      />

      {/* 消耗升级：作废 1 个未绑定码，试用码原地升级（ADR-0014） */}
      <UpgradeTrialModal
        open={upgradeOpen}
        onClose={() => setUpgradeOpen(false)}
        onUpgraded={() => {
          setUpgradeOpen(false);
          void loadCodes();
          setPurchasedRefreshKey((k) => k + 1);
        }}
      />
    </div>
  );
}

/** 所属人视角（P-E，ADR-0010/0014）：我购买的码，平铺列表 + 每码「去向」备注。
 *
 * 口径（2026-08-24 起）：订单详情（商品/金额/订单号）只在「订单记录」tab 展示；
 * 本区只回答「每枚码现在去哪了/用得怎么样」——未绑定/已绑定自己/已绑定他人/已用于升级/已作废 + 报告状态。
 */
function PurchasedCodesSection({
  t,
  copiedText,
  onCopy,
  onUse,
  refreshKey = 0,
  uiPreview = false,
}: {
  t: (k: string, params?: Record<string, string>) => string;
  copiedText: string | null;
  onCopy: (text: string) => void;
  onUse: (code: string) => void;
  /** 递增触发重新拉取（升级/延期后码去向会变） */
  refreshKey?: number;
  /** 本地视觉预览不访问登录态接口，避免触发全局登录弹窗。 */
  uiPreview?: boolean;
}) {
  const [items, setItems] = useState<PurchasedCodeItem[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (uiPreview) {
      setItems([]);
      setLoaded(true);
      return;
    }
    fetchMyPurchasedCodes()
      .then(setItems)
      .catch((e: unknown) => {
        // 请求取消：保留已有数据；其余错误仅首次置空
        if (isRequestCanceled(e)) return;
        setItems([]);
      })
      .finally(() => setLoaded(true));
  }, [refreshKey, uiPreview]);

  if (!loaded || items.length === 0) return null;

  // 平铺展示：按创建时间倒序（最新的码在最前）
  const sorted = [...items].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''));

  /** 单个码一行：码值 + 状态 badge + 去向备注（合并激活情况） + 报告状态；未绑定码保留复制/去使用 */
  const renderCodeRow = (item: PurchasedCodeItem) => {
    const isConsumed = item.status === 'consumed';
    const isRevoked = item.status === 'revoked';
    const unbound = !item.activated && !isConsumed && !isRevoked;
    return (
      <div key={item.code} className="p-4 flex flex-wrap items-center gap-3">
        <span className="font-mono text-sm text-bd-fg">{item.code}</span>
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${STATUS_COLOR[item.status] || 'bg-neutral-100 text-neutral-500 border-neutral-200'}`}>
          {t(`dashboard.codesPage.status.${item.status}`)}
        </span>
        <span className="text-xs text-bd-muted">
          {isConsumed ? (
            <>
              {t('dashboard.codesPage.destination.consumedForUpgrade')}
              {item.consumed_into && (
                <span className="ml-1 font-mono tracking-wider text-bd-fg">
                  {item.consumed_into}
                </span>
              )}
            </>
          ) : isRevoked ? (
            t('dashboard.codesPage.destination.revoked')
          ) : item.activated ? (
            item.activated_by_self
              ? t('dashboard.codesPage.destination.boundSelf')
              : t('dashboard.codesPage.destination.boundOther', { email: item.activated_by ?? '' })
          ) : (
            t('dashboard.codesPage.destination.unbound')
          )}
        </span>
        {unbound && (
          <>
            <button
              type="button"
              onClick={() => onCopy(item.code)}
              className="inline-flex items-center gap-1 rounded-lg border border-bd-border px-2 py-1 text-[11px] text-bd-muted transition hover:bg-bd-overlay-md hover:text-bd-fg"
            >
              {copiedText === item.code ? (
                <>
                  <Check className="h-3 w-3 text-emerald-500" />
                  {t('dashboard.codesPage.copied')}
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  {t('dashboard.codesPage.copy')}
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() => onUse(item.code)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-bd-ui-accent px-3 py-1.5 text-xs font-medium text-bd-ui-accent-fg transition hover:opacity-90"
            >
              {t('dashboard.codesPage.goUse')}
            </button>
          </>
        )}
        <span className="ml-auto text-xs">
          {item.has_report ? (
            item.report_authorized ? (
              <span className="text-emerald-600">{t('dashboard.codesPage.reportAuthorized')}</span>
            ) : (
              <span className="text-amber-600">{t('dashboard.codesPage.reportNotAuthorized')}</span>
            )
          ) : item.report_status === 'pending_review' ? (
            <span className="text-amber-600">{t('dashboard.codesPage.reportReviewing')}</span>
          ) : (
            <span className="text-bd-subtle">{t('dashboard.codesPage.reportNotReady')}</span>
          )}
        </span>
      </div>
    );
  };

  return (
    <section className="mt-10 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-bd-fg">{t('dashboard.codesPage.purchasedTitle')}</h2>
        <p className="text-xs text-bd-muted mt-1">{t('dashboard.codesPage.purchasedDesc')}</p>
      </div>
      <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm overflow-hidden">
        <div className="divide-y divide-bd-border">{sorted.map(renderCodeRow)}</div>
      </div>
    </section>
  );
}

function PreviewTabPlaceholder({ title, description }: { title: string; description: string }) {
  return (
    <section className="ol-profile-surface p-8 text-center">
      <Ticket className="mx-auto mb-3 h-7 w-7 text-bd-muted" />
      <h3 className="text-base font-semibold text-bd-fg">{title}</h3>
      <p className="mt-2 text-sm text-bd-muted">{description}</p>
    </section>
  );
}
