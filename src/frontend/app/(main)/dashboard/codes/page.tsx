'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, Copy, Ticket } from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import { listMyCodes, type CodeType, type MyCodeItem } from '@/lib/api/activation';
import { setLastActivationCode } from '@/lib/explore/session';
import { fetchMyPurchasedCodes, type PurchasedCodeItem } from '@/lib/api/teamAnalysis';
import { formatLocalDateTime, toDate } from '@/lib/utils/formatTime';
import PurchaseModal from '@/components/payment/PurchaseModal';
import { useLocale } from '@/hooks/useLocale';

/** 状态 badge 配色：active 绿 / inactive 橙 / expired 灰 / revoked 红 / 其他 灰 */
const STATUS_COLOR: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  inactive: 'bg-orange-100 text-orange-700 border-orange-200',
  expired: 'bg-neutral-200 text-neutral-600 border-neutral-300',
  revoked: 'bg-red-100 text-red-700 border-red-200',
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
  t,
}: {
  item: MyCodeItem;
  copied: boolean;
  onCopy: (text: string) => void;
  onUse: (code: string) => void;
  onRenew: (code: string) => void;
  t: (k: string, params?: Record<string, string>) => string;
}) {
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
        {codeType === 'full' && (
          <button
            type="button"
            onClick={() => onRenew(item.code)}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-bd-border px-3 py-1.5 text-xs font-medium text-bd-muted transition hover:bg-bd-overlay-md hover:text-bd-fg"
          >
            {t('dashboard.codesPage.renew')}
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
            {item.has_report
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

  const [codes, setCodes] = useState<MyCodeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedText, setCopiedText] = useState<string | null>(null);
  /** 延期激活目标码：非 null 时打开 PurchaseModal 延期模式 */
  const [renewalTarget, setRenewalTarget] = useState<string | null>(null);

  const loadCodes = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listMyCodes();
      setCodes(items);
      setError(null);
    } catch (e: unknown) {
      setError(getApiErrorMessage(e, t('dashboard.codesPage.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadCodes();
  }, [loadCodes]);

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedText(text);
      setTimeout(() => setCopiedText(null), 1500);
    } catch {
      /* 复制失败静默 */
    }
  };

  /** 去使用：写入「上次激活码」并跳激活页（code 由激活页从 query 预填） */
  const handleUse = (code: string) => {
    setLastActivationCode(code);
    router.push(`/explore/activate?code=${encodeURIComponent(code)}`);
  };

  return (
    <div className="max-w-4xl">
      <div className="mb-8 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-bd-fg">{t('dashboard.myCodes')}</h1>
      </div>

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
              t={t}
            />
          ))}
        </div>
      )}

      {/* 所属人视角（P-E）：我购买的码（含送出的赠品码） */}
      <PurchasedCodesSection t={t} />

      {/* 延期激活：关闭后刷新列表（有效期可能已追加） */}
      <PurchaseModal
        open={renewalTarget !== null}
        onClose={() => {
          setRenewalTarget(null);
          void loadCodes();
        }}
        renewalTargetCode={renewalTarget ?? undefined}
      />
    </div>
  );
}

/** 所属人视角（P-E，ADR-0010）：我购买的码——被谁激活、报告就绪/授权状态 */
function PurchasedCodesSection({ t }: { t: (k: string, params?: Record<string, string>) => string }) {
  const [items, setItems] = useState<PurchasedCodeItem[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchMyPurchasedCodes()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded || items.length === 0) return null;

  return (
    <section className="mt-10 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-bd-fg">{t('dashboard.codesPage.purchasedTitle')}</h2>
        <p className="text-xs text-bd-muted mt-1">{t('dashboard.codesPage.purchasedDesc')}</p>
      </div>
      <div className="space-y-3">
        {items.map((item) => (
          <div
            key={item.code}
            className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-4 flex flex-wrap items-center gap-3"
          >
            <span className="font-mono text-sm text-bd-fg">{item.code}</span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${STATUS_COLOR[item.status] || 'bg-neutral-100 text-neutral-500 border-neutral-200'}`}>
              {t(`dashboard.codesPage.status.${item.status}`)}
            </span>
            <span className="text-xs text-bd-muted">
              {item.activated
                ? item.activated_by_self
                  ? t('dashboard.codesPage.activatedBySelf')
                  : t('dashboard.codesPage.activatedBy', { email: item.activated_by ?? '' })
                : t('dashboard.codesPage.notActivated')}
            </span>
            <span className="ml-auto text-xs">
              {item.has_report ? (
                item.report_authorized ? (
                  <span className="text-emerald-600">{t('dashboard.codesPage.reportAuthorized')}</span>
                ) : (
                  <span className="text-amber-600">{t('dashboard.codesPage.reportNotAuthorized')}</span>
                )
              ) : (
                <span className="text-bd-subtle">{t('dashboard.codesPage.reportNotReady')}</span>
              )}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
