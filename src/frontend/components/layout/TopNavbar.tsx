'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { NAV_ITEMS } from '@/lib/nav';
import { useState } from 'react';
import { Menu, X } from 'lucide-react';

export default function TopNavbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, user, logout } = useAuthStore();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleNavClick = (item: typeof NAV_ITEMS[number], e: React.MouseEvent) => {
    if (item.requiresAuth && !isAuthenticated) {
      e.preventDefault();
      router.push(`/auth/login?redirect=${encodeURIComponent(item.href)}`);
    }
    setMobileOpen(false);
  };

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-14 bg-slate-900/95 backdrop-blur border-b border-white/10">
      <div className="max-w-7xl mx-auto h-full px-4 flex items-center justify-between">
        {/* Brand */}
        <Link href="/" className="text-lg font-bold text-white whitespace-nowrap">
          找到想做的事
        </Link>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={(e) => handleNavClick(item, e)}
                className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-primary-500/20 text-primary-300'
                    : 'text-white/70 hover:text-white hover:bg-white/10'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>

        {/* Right side: auth */}
        <div className="hidden md:flex items-center gap-3">
          {isAuthenticated ? (
            <>
              <span className="text-sm text-white/60">
                {user?.username || user?.email || '用户'}
              </span>
              <button
                type="button"
                onClick={handleLogout}
                className="px-3 py-1.5 rounded-lg text-sm text-white/70 hover:text-white hover:bg-white/10 transition-colors"
              >
                退出
              </button>
            </>
          ) : (
            <Link
              href="/auth/login"
              className="px-4 py-1.5 rounded-lg text-sm bg-primary-500 hover:bg-primary-400 text-white transition-colors"
            >
              登录 / 注册
            </Link>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden p-2 text-white/70 hover:text-white"
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden bg-slate-900/98 border-b border-white/10 px-4 pb-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={(e) => handleNavClick(item, e)}
                className={`block px-3 py-2 rounded-lg text-sm ${
                  isActive
                    ? 'bg-primary-500/20 text-primary-300'
                    : 'text-white/70 hover:text-white hover:bg-white/10'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <div className="pt-2 border-t border-white/10">
            {isAuthenticated ? (
              <button
                type="button"
                onClick={() => { handleLogout(); setMobileOpen(false); }}
                className="block w-full text-left px-3 py-2 rounded-lg text-sm text-white/70 hover:text-white hover:bg-white/10"
              >
                退出（{user?.username || user?.email || '用户'}）
              </button>
            ) : (
              <Link
                href="/auth/login"
                onClick={() => setMobileOpen(false)}
                className="block px-3 py-2 rounded-lg text-sm bg-primary-500/20 text-primary-300"
              >
                登录 / 注册
              </Link>
            )}
          </div>
        </div>
      )}
    </nav>
  );
}
