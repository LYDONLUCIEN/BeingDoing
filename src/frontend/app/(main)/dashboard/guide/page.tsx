'use client';

import { useLocale } from '@/hooks/useLocale';

export default function DashboardGuidePage() {
  const { t } = useLocale();

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-bd-fg mb-8">{t('dashboard.usageGuide')}</h1>
      <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8">
        <p className="text-bd-muted">使用指南内容开发中。</p>
      </div>
    </div>
  );
}
