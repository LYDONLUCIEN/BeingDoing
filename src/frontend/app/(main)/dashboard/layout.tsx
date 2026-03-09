'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { User, BarChart3, BookOpen, HelpCircle, Trash2, Settings } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useLocale } from '@/hooks/useLocale';

const NAV_ITEMS = [
  { path: '/dashboard', icon: User, labelKey: 'dashboard.currentProgress' },
  { path: '/dashboard/report', icon: BarChart3, labelKey: 'dashboard.report' },
  { path: '/dashboard/guide', icon: BookOpen, labelKey: 'dashboard.usageGuide' },
  { path: '/dashboard/help', icon: HelpCircle, labelKey: 'dashboard.helpCenter' },
  { path: '/dashboard/recycle', icon: Trash2, labelKey: 'dashboard.recycleBin' },
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

  const displayName = user?.username || user?.email || t('common.user');
  const initials = (user?.username || user?.email || 'U')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] bg-bd-bg">
      <aside className="w-64 bg-bd-card/80 backdrop-blur-lg border-r border-bd-border fixed left-0 top-14 bottom-0 flex flex-col items-center pt-8 px-4 z-20">
        <div
          className="w-20 h-20 rounded-full flex items-center justify-center text-white text-2xl font-semibold mb-3 overflow-hidden ring-2 ring-black/20 ring-offset-2 ring-offset-bd-card shadow-[0_2px_8px_rgba(0,0,0,0.15)]"
          style={{
            background: user?.avatar_url
              ? `url(${user.avatar_url}) center/cover`
              : 'linear-gradient(135deg, var(--bd-phase-values), var(--bd-phase-strengths))',
          }}
        >
          {!user?.avatar_url && initials}
        </div>
        <h3 className="font-medium text-bd-fg mb-8 truncate max-w-full px-2 text-center">
          {displayName}
        </h3>

        <nav className="w-full space-y-2">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.path === '/dashboard'
                ? pathname === '/dashboard'
                : pathname.startsWith(item.path);
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                  isActive
                    ? 'bg-bd-ui-accent text-bd-ui-accent-fg'
                    : 'text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md'
                }`}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <span className="text-sm">{t(item.labelKey)}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <main className="ml-64 flex-1 p-8 min-w-0">{children}</main>
    </div>
  );
}
