'use client';

import Link from 'next/link';
import { useLocale } from '@/hooks/useLocale';

export default function DashboardReportPage() {
  const { t } = useLocale();

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-bd-fg mb-8">{t('dashboard.report')}</h1>
      <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
        <p className="text-bd-muted mb-6">综合报告功能开发中，请从探索流程完成后查看。</p>
        <Link
          href="/explore/report/view"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
        >
          {t('common.viewReport')}
        </Link>
      </div>
    </div>
  );
}
