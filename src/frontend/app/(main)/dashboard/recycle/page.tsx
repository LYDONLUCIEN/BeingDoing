'use client';

import { RotateCcw } from 'lucide-react';
import DashboardPageHeader from '@/components/dashboard/DashboardPageHeader';
import { useLocale } from '@/hooks/useLocale';

export default function DashboardRecyclePage() {
  const { t } = useLocale();

  return (
    <div className="ol-profile-content">
      <DashboardPageHeader
        kicker="RECYCLE BIN"
        title={t('dashboard.recycleBin')}
        description="删除记录的恢复能力尚未上线；未来会在这里保留可恢复的旅程与对话。"
      />
      <section className="ol-profile-empty ol-profile-surface">
        <span><RotateCcw aria-hidden="true" /></span>
        <h3>当前没有可恢复的记录</h3>
        <p>回收与恢复功能正在开发中，现阶段不会在这里执行任何数据操作。</p>
      </section>
    </div>
  );
}
