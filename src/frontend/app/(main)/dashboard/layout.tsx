'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ArrowLeft, User, BookOpen, CalendarCheck, HelpCircle, Trash2, Settings, Ticket, UsersRound } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useLocale } from '@/hooks/useLocale';

const NAV_ITEMS = [
  { path: '/dashboard', icon: User, labelKey: 'dashboard.currentProgress' },
  { path: '/dashboard/guide', icon: BookOpen, labelKey: 'dashboard.usageGuide' },
  { path: '/dashboard/help', icon: HelpCircle, labelKey: 'dashboard.helpCenter' },
  { path: '/dashboard/recycle', icon: Trash2, labelKey: 'dashboard.recycleBin' },
  { path: '/dashboard/codes', icon: Ticket, labelKey: 'dashboard.myCodes' },
  { path: '/dashboard/consultation', icon: CalendarCheck, label: '报告解读' },
  { path: '/dashboard/team-analysis', icon: UsersRound, labelKey: 'dashboard.teamAnalysis' },
  { path: '/dashboard/settings', icon: Settings, labelKey: 'dashboard.setting' },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { t } = useLocale();
  const { user } = useAuthStore();
  const [mounted, setMounted] = useState(false);

  // 首帧统一占位，避免 SSR/客户端 auth 状态不一致导致 React 418/423 水合错误
  useEffect(() => {
    setMounted(true);
    document.documentElement.setAttribute('data-profile-page', 'true');
    return () => document.documentElement.removeAttribute('data-profile-page');
  }, []);

  if (!mounted) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-6">
        <div className="text-sm text-bd-muted">加载中…</div>
      </div>
    );
  }

  const displayName = user?.username || user?.email || t('common.user');
  const initials = (user?.username || user?.email || 'U')
    .slice(0, 2)
    .toUpperCase();
  const previewSuffix =
    process.env.NODE_ENV === 'development' &&
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('ui_preview') === '1'
      ? '?ui_preview=1'
      : '';

  return (
    <div className="ol-profile-app">
      <div className="ol-profile-backdrop" aria-hidden="true">
        <span className="ol-profile-glow ol-profile-glow-blue" />
        <span className="ol-profile-glow ol-profile-glow-green" />
        <span className="ol-profile-glow ol-profile-glow-gold" />
        <span className="ol-profile-glow ol-profile-glow-coral" />
      </div>
      <svg className="ol-profile-line-art" viewBox="0 0 520 260" aria-hidden="true">
        <path d="M6 248C94 236 135 172 204 179c66 7 72 75 146 55 54-15 68-76 126-88" />
        <path className="ol-profile-leaf" d="M396 187c-4-40 12-73 44-96M417 139c-18-16-37-16-55-3 19 18 38 18 55 3ZM430 111c7-22 22-35 45-37-4 25-19 38-45 37Z" />
        <circle cx="204" cy="179" r="4" />
        <circle cx="350" cy="234" r="4" />
      </svg>

      <div className="ol-profile-page">
        <header className="ol-profile-masthead">
          <div>
            <p className="ol-profile-kicker">PERSONAL SPACE</p>
            <h1>我的空间</h1>
            <p>回看走过的路，也从这里继续。</p>
          </div>
          <Link href="/" className="ol-profile-back">
            <ArrowLeft aria-hidden="true" />
            返回首页
          </Link>
        </header>

        <div className="ol-profile-layout">
          <aside className="ol-profile-sidebar" aria-label="个人空间导航">
            <section className="ol-profile-identity">
              <span
                className="ol-profile-avatar"
                style={{
                  background: user?.avatar_url
                    ? `url(${user.avatar_url}) center/cover`
                    : 'linear-gradient(145deg, #79a9e0, #72b7a1)',
                }}
              >
                {!user?.avatar_url && initials}
              </span>
              <div>
                <strong>{displayName}</strong>
                <small>{user?.email || user?.phone || 'OpenLife 探索者'}</small>
              </div>
              <Link href={`/dashboard/profile/edit${previewSuffix}`}>编辑资料</Link>
            </section>

            <nav className="ol-profile-nav">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive = item.path === '/dashboard'
                  ? pathname === '/dashboard'
                  : pathname.startsWith(item.path);
                return (
                  <Link
                    key={item.path}
                    href={`${item.path}${previewSuffix}`}
                    aria-current={isActive ? 'page' : undefined}
                  >
                    <Icon aria-hidden="true" />
                    <span>{'label' in item ? item.label : t(item.labelKey)}</span>
                  </Link>
                );
              })}
            </nav>
            <p className="ol-profile-side-note">
              你的记录只属于你。<br />
              随时可以回看、导出或删除。
            </p>
          </aside>

          <main className="ol-profile-main">{children}</main>
        </div>
      </div>
    </div>
  );
}
