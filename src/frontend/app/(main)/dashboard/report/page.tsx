'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Clock, FileText, Ticket } from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import { getMyReports, type MyReportListItem } from '@/lib/api/report';
import { formatLocalDateTime } from '@/lib/utils/formatTime';
import { useLocale } from '@/hooks/useLocale';

/** 报告卡片：仅展示 pending_review / approved 两种状态 */
function ReportCard({ item, t }: { item: MyReportListItem; t: (k: string, params?: Record<string, string>) => string }) {
  const { locale } = useLocale();
  const isPending = item.review_status === 'pending_review';

  const deadlineText = useMemo(() => {
    if (!item.review_deadline) return null;
    const d = new Date(item.review_deadline);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }, [item.review_deadline, locale]);

  const createdAt = (() => {
    if (!item.created_at) return '—';
    const formatted = formatLocalDateTime(item.created_at);
    return formatted === '-' ? item.created_at : formatted;
  })();

  return (
    <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-bd-overlay-md">
          <FileText className="h-5 w-5 text-bd-muted" />
        </div>
        <div className="min-w-0">
          <p className="text-[10px] text-bd-muted">{t('dashboard.reportPage.codeLabel')}</p>
          <p className="font-mono text-base font-semibold tracking-wider text-bd-fg">
            {item.activation_code}
          </p>
        </div>
        <span
          className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
            isPending
              ? 'bg-amber-100 text-amber-700 border-amber-200'
              : 'bg-emerald-100 text-emerald-700 border-emerald-200'
          }`}
        >
          {isPending
            ? t('dashboard.reportPage.statusPending')
            : t('dashboard.reportPage.statusApproved')}
        </span>
        <Link
          href={`/explore/report/view?code=${encodeURIComponent(item.activation_code)}`}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-bd-ui-accent px-3 py-1.5 text-xs font-medium text-bd-ui-accent-fg transition hover:opacity-90"
        >
          {t('dashboard.reportPage.viewReport')}
        </Link>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div className="space-y-0.5">
          <p className="text-[10px] text-bd-muted">{t('dashboard.reportPage.createdAt')}</p>
          <p className="text-bd-fg">{createdAt}</p>
        </div>
        {isPending && deadlineText && (
          <div className="space-y-0.5">
            <p className="flex items-center gap-1 text-[10px] text-bd-muted">
              <Clock className="h-3 w-3" />
              {t('dashboard.reportPage.deadlineLabel')}
            </p>
            <p className="text-bd-fg">{deadlineText}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardReportPage() {
  const { t } = useLocale();

  const [items, setItems] = useState<MyReportListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getMyReports();
      setItems(res);
      setError(null);
    } catch (e: unknown) {
      setError(getApiErrorMessage(e, t('dashboard.reportPage.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  /** 只展示审核中 / 已生成的报告 */
  const visible = items.filter(
    (it) => it.review_status === 'pending_review' || it.review_status === 'approved',
  );
  /** 存在未解锁的报告（五阶段未完成） */
  const hasNotStarted = items.some((it) => it.review_status === 'not_started');

  return (
    <div className="max-w-4xl">
      <div className="mb-8 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-bd-fg">{t('dashboard.report')}</h1>
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
            onClick={() => void load()}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : visible.length > 0 ? (
        <div className="space-y-4">
          {visible.map((item) => (
            <ReportCard key={item.report_id} item={item} t={t} />
          ))}
        </div>
      ) : hasNotStarted ? (
        /* 空态①：有码但五阶段未完成 */
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-12 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-bd-overlay-md">
            <FileText className="h-6 w-6 text-bd-muted" />
          </div>
          <p className="text-bd-fg font-medium">{t('dashboard.reportPage.emptyLockedTitle')}</p>
          <p className="mt-1 text-sm text-bd-muted">{t('dashboard.reportPage.emptyLockedDesc')}</p>
          <Link
            href="/explore"
            className="mt-6 inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            {t('dashboard.reportPage.emptyLockedCta')}
          </Link>
        </div>
      ) : (
        /* 空态②：无任何报告记录，引导激活/购买完整码 */
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-12 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-bd-overlay-md">
            <Ticket className="h-6 w-6 text-bd-muted" />
          </div>
          <p className="text-bd-fg font-medium">{t('dashboard.reportPage.emptyNoneTitle')}</p>
          <p className="mt-1 text-sm text-bd-muted">{t('dashboard.reportPage.emptyNoneDesc')}</p>
          <Link
            href="/dashboard/codes"
            className="mt-6 inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            {t('dashboard.reportPage.emptyNoneCta')}
          </Link>
        </div>
      )}
    </div>
  );
}
