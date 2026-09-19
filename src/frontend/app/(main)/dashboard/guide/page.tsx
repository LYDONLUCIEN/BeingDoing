'use client';

import Link from 'next/link';
import type { CSSProperties } from 'react';
import DashboardPageHeader from '@/components/dashboard/DashboardPageHeader';
import { useLocale } from '@/hooks/useLocale';

const GUIDE_ITEMS = [
  {
    number: '01',
    title: '从真实经历开始',
    description: '不用寻找标准答案，只要说出此刻最真实的感受和困惑。',
    cta: '开始或继续探索',
    href: '/explore/activate',
    color: '#5e91e6',
  },
  {
    number: '02',
    title: '让线索彼此连接',
    description: '优势、热爱与使命不是孤立标签，它们会逐渐组成你的判断体系。',
    cta: '查看我的进度',
    href: '/dashboard',
    color: '#5eb48f',
  },
  {
    number: '03',
    title: '在对话中澄清',
    description: '对话没有固定轮次，直到你感觉一些模糊的东西开始变得清晰。',
    cta: '回到我的旅程',
    href: '/dashboard',
    color: '#eb7f84',
  },
  {
    number: '04',
    title: '把理解带进行动',
    description: '沉淀多个方向，比较、验证，再形成属于你的职业探索报告。',
    cta: '查看旅程与报告',
    href: '/dashboard',
    color: '#8f78d8',
  },
];

export default function DashboardGuidePage() {
  const { t } = useLocale();

  return (
    <div className="ol-profile-content">
      <DashboardPageHeader
        kicker="HOW IT WORKS"
        title={t('dashboard.usageGuide')}
        description="不需要一次走完。每个阶段都可以独立深入，也可以随时回来继续。"
      />
      <div className="ol-profile-guide-grid">
        {GUIDE_ITEMS.map((item) => (
          <article key={item.number} style={{ '--guide-color': item.color } as CSSProperties}>
            <span>{item.number}</span>
            <h3>{item.title}</h3>
            <p>{item.description}</p>
            <Link href={item.href}>{item.cta} →</Link>
          </article>
        ))}
      </div>
    </div>
  );
}
