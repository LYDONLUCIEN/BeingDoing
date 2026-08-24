'use client';

/**
 * 团队分析页（占位版，2026-08-24 起）
 * /dashboard/team-analysis
 *
 * 团队报告解析能力暂未开放：页面只展示「开发中」占位 + 联系邮箱。
 * 原完整实现保留在同目录 page.impl.tsx，正式上线时用它替换本文件即可。
 */

import { useEffect, useState } from 'react';
import { Mail, UsersRound } from 'lucide-react';
import { useLocale } from '@/hooks/useLocale';
import { getTeamAnalysisEmail } from '@/lib/api/payment';

export default function TeamAnalysisPage() {
  const { t } = useLocale();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    void getTeamAnalysisEmail().then(setEmail);
  }, []);

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-16 text-center space-y-5">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-bd-overlay-md">
          <UsersRound className="h-8 w-8 text-bd-muted" />
        </div>
        <div className="space-y-2">
          <span className="inline-block rounded-full border border-amber-300 bg-amber-50 px-3 py-0.5 text-xs font-medium text-amber-700">
            {t('team.comingSoonBadge')}
          </span>
          <h1 className="text-2xl font-bold text-bd-fg">{t('team.comingSoonTitle')}</h1>
          <p className="mx-auto max-w-md text-sm text-bd-muted">{t('team.comingSoonDesc')}</p>
        </div>
        {email && (
          <p className="inline-flex items-center gap-2 text-sm text-bd-muted">
            <Mail className="h-4 w-4" />
            {t('team.comingSoonContact')}
            <a
              href={`mailto:${email}`}
              className="font-medium text-bd-ui-accent hover:underline"
            >
              {email}
            </a>
          </p>
        )}
      </div>
    </div>
  );
}
