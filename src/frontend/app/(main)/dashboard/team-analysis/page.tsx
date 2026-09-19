'use client';

import { useState } from 'react';
import { Mail } from 'lucide-react';
import DashboardPageHeader from '@/components/dashboard/DashboardPageHeader';
import { useLocale } from '@/hooks/useLocale';

/** 团队分析页占位期联系邮箱（保持现有产品口径）。 */
const CONTACT_EMAIL = 'openlife.lab@outlook.com';

export default function TeamAnalysisPage() {
  const { t } = useLocale();
  const [showNotice, setShowNotice] = useState(false);

  return (
    <div className="ol-profile-content">
      <DashboardPageHeader
        kicker="TEAM INSIGHT"
        title={t('dashboard.teamAnalysis')}
        description="在尊重个人隐私的前提下，看见团队的优势组合与协作方式。"
      />

      <section className="ol-profile-team-card ol-profile-surface">
        <div className="ol-profile-team-visual" aria-hidden="true">
          <i /><i /><i /><i /><i />
        </div>
        <div>
          <span>团队版 · 开发中</span>
          <h3>把不同的人，放在更合适的位置</h3>
          <p>{t('team.comingSoonDesc')}</p>
          <p>团队报告解析能力暂未开放。如需了解后续计划或申请团队服务，可先通过邮箱联系我们。</p>
          <button type="button" className="ol-profile-primary" onClick={() => setShowNotice(true)}>
            创建团队
          </button>
          {showNotice && (
            <div className="ol-team-notice" role="status">
              <strong>{t('team.comingSoonTitle')}</strong>
              <span>
                <Mail aria-hidden="true" />
                <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
              </span>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
