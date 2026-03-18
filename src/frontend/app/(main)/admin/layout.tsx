'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BarChart3, KeyRound, MessageSquare, FileText, Activity, TerminalSquare, Settings } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useLocale } from '@/hooks/useLocale';

const ADMIN_NAV_ITEMS = [
  { path: '/admin', icon: BarChart3, label: '总览 Dashboard' },
  { path: '/admin/activations', icon: KeyRound, label: '激活码管理' },
  { path: '/admin/conversations', icon: MessageSquare, label: '对话与阶段' },
  { path: '/admin/reports', icon: FileText, label: '报告概览' },
  { path: '/admin/analytics', icon: Activity, label: '埋点与 Token 统计' },
  { path: '/admin/logs', icon: TerminalSquare, label: '日志与调试' },
  { path: '/admin/system', icon: Settings, label: '系统设置' },
] as const;

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { t } = useLocale();
  const { user, isAuthenticated } = useAuthStore();

  const isAdmin = !!(isAuthenticated && user?.is_super_admin);
  const displayName = user?.username || user?.email || t('common.user');
  const initials = (user?.username || user?.email || 'U')
    .slice(0, 2)
    .toUpperCase();

  if (!isAdmin) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-6">
        <div className="max-w-md w-full bg-bd-card/80 backdrop-blur-xl border border-bd-border rounded-3xl px-8 py-10 shadow-[0_22px_45px_rgba(15,23,42,0.16)] text-center">
          <h1 className="text-xl font-semibold mb-3" style={{ color: 'var(--bd-fg)' }}>
            Admin 控制台
          </h1>
          <p className="text-sm mb-6" style={{ color: 'var(--bd-fg-muted)' }}>
            当前账号没有管理员权限。请确认后端环境变量 <code className="px-1 py-0.5 rounded bg-bd-overlay-md text-xs">SUPER_ADMIN_EMAILS</code>{' '}
            或 <code className="px-1 py-0.5 rounded bg-bd-overlay-md text-xs">SUPER_ADMIN_USER_IDS</code> 是否包含你的账号。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] bg-bd-bg">
      <aside className="w-68 bg-bd-card/90 backdrop-blur-2xl border-r border-bd-border fixed left-0 top-14 bottom-0 flex flex-col items-center pt-8 px-5 z-30">
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center text-white text-lg font-semibold mb-3 overflow-hidden ring-2 ring-black/15 ring-offset-2 ring-offset-bd-card shadow-[0_4px_16px_rgba(15,23,42,0.28)]"
          style={{
            background: user?.avatar_url
              ? `url(${user.avatar_url}) center/cover`
              : 'linear-gradient(145deg, var(--bd-phase-values), var(--bd-phase-strengths))',
          }}
        >
          {!user?.avatar_url && initials}
        </div>
        <p className="text-xs uppercase tracking-[0.16em] text-bd-subtle mb-1">
          Admin
        </p>
        <h3 className="font-medium text-sm text-bd-fg mb-8 truncate max-w-full px-2 text-center">
          {displayName}
        </h3>

        <nav className="w-full space-y-1">
          {ADMIN_NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.path === '/admin'
                ? pathname === '/admin'
                : pathname.startsWith(item.path);
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition-all ${
                  isActive
                    ? 'bg-bd-ui-accent text-bd-ui-accent-fg shadow-[0_16px_36px_rgba(15,23,42,0.25)]'
                    : 'text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md'
                }`}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <p className="mt-auto mb-6 text-[10px] text-bd-subtle/80 text-center leading-relaxed px-2">
          仅超级管理员可访问 Admin 控制台。
          <br />
          数据来源于 simple-chat 历史与 analytics 聚合。
        </p>
      </aside>

      <main className="ml-68 flex-1 p-8 min-w-0">{children}</main>
    </div>
  );
}

