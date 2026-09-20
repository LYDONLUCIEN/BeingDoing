'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, Ticket } from 'lucide-react';
import { getApiErrorMessage, isRequestCanceled } from '@/lib/api/client';
import {
  fenToYuan,
  listMyCoupons,
  type CouponSource,
  type MyCouponItem,
  type MyCouponsResult,
} from '@/lib/api/payment';
import { toDate } from '@/lib/utils/formatTime';
import { useLocale } from '@/hooks/useLocale';

/** 来源 badge：统一走 .ol-pill 体系（email_auto 邮件赠送 蓝 / admin 活动发放 琥珀） */
const SOURCE_COLOR: Record<CouponSource, string> = {
  email_auto: 'ol-pill--blue',
  admin: 'ol-pill--amber',
};

/** 有效期至 YYYY-MM-DD（本地时区） */
function formatDay(iso?: string | null): string {
  const d = toDate(iso);
  if (!d) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 我的折扣券（/dashboard/codes 第三个 tab）：可用 / 已使用 / 已过期 三组展示 */
export default function CouponsSection() {
  const { t } = useLocale();

  const [groups, setGroups] = useState<MyCouponsResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listMyCoupons();
      setGroups(res);
      setError(null);
    } catch (e: unknown) {
      // 页面刷新/导航导致的请求取消不是错误，静默忽略（保留已有数据）
      if (isRequestCanceled(e)) return;
      setError(getApiErrorMessage(e, t('dashboard.couponsSection.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedCode(text);
      setTimeout(() => setCopiedCode(null), 1500);
    } catch {
      /* 复制失败静默 */
    }
  };

  const isEmpty =
    !groups ||
    (groups.available.length === 0 && groups.used.length === 0 && groups.expired.length === 0);

  /** 单券卡片：dimmed=true 时整卡灰显（已过期组） */
  const renderCoupon = (item: MyCouponItem, dimmed: boolean) => (
    <div
      key={item.code}
      className={`bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-5 ${
        dimmed ? 'opacity-60' : ''
      }`}
    >
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-base font-semibold text-bd-fg">¥{fenToYuan(item.amount)}</span>
        <button
          type="button"
          onClick={() => void copyText(item.code)}
          className="inline-flex items-center gap-1 rounded-lg border border-bd-border px-2 py-1 font-mono text-[11px] tracking-wider text-bd-muted transition hover:bg-bd-overlay-md hover:text-bd-fg"
        >
          {item.code}
          {copiedCode === item.code ? (
            <Check className="h-3 w-3 text-emerald-500" />
          ) : (
            <Copy className="h-3 w-3 opacity-60" />
          )}
        </button>
        <span
          className={`ol-pill ${SOURCE_COLOR[item.source]}`}
        >
          {t(`dashboard.couponsSection.source.${item.source}`)}
        </span>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-bd-muted">
        <span>
          {t('dashboard.couponsSection.expiresLabel')}
          {item.expires_at ? formatDay(item.expires_at) : t('dashboard.codesPage.noExpiry')}
        </span>
        {item.used_at && (
          <span>
            {t('dashboard.couponsSection.usedAt')}
            {formatDay(item.used_at)}
          </span>
        )}
        {item.used_order_no && (
          <span className="font-mono">
            {t('dashboard.couponsSection.orderNo')}
            {item.used_order_no}
          </span>
        )}
      </div>
    </div>
  );

  const renderGroup = (title: string, items: MyCouponItem[], dimmed: boolean) =>
    items.length === 0 ? null : (
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-bd-muted">
          {title}
          <span className="ml-1.5 text-xs text-bd-subtle">({items.length})</span>
        </h2>
        <div className="space-y-3">{items.map((item) => renderCoupon(item, dimmed))}</div>
      </div>
    );

  return (
    <div>
      {loading ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-bd-muted">{t('common.loading')}</p>
        </div>
      ) : error && isEmpty ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-red-600/90 dark:text-red-400/90 mb-4">{error}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : isEmpty ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-12 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-bd-overlay-md">
            <Ticket className="h-6 w-6 text-bd-muted" />
          </div>
          <p className="text-bd-muted">{t('dashboard.couponsSection.empty')}</p>
        </div>
      ) : (
        <div className="space-y-6">
          {renderGroup(t('dashboard.couponsSection.groupAvailable'), groups!.available, false)}
          {renderGroup(t('dashboard.couponsSection.groupUsed'), groups!.used, false)}
          {renderGroup(t('dashboard.couponsSection.groupExpired'), groups!.expired, true)}
        </div>
      )}
    </div>
  );
}
