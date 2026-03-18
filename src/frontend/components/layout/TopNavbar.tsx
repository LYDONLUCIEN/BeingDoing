'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useAuthModalStore } from '@/stores/authModalStore';
import { useThemeStore } from '@/stores/themeStore';
import { useLocaleStore } from '@/stores/localeStore';
import { onAuthRequired } from '@/lib/api/client';
import { NAV_ITEMS } from '@/lib/nav';
import { useLocale } from '@/hooks/useLocale';
import { useState, useEffect, useRef } from 'react';
import { Menu, X, Sun, Moon } from 'lucide-react';
import AuthModal from './AuthModal';

export default function TopNavbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const { t } = useLocale(mounted ? undefined : 'zh');
  const { isAuthenticated, user, logout, _hasHydrated } = useAuthStore();
  const { colorScheme } = useThemeStore();
  const { locale, setLocale } = useLocaleStore();
  // 挂载后且已登录则显示头像；不依赖 _hasHydrated，避免登录后 persist 未完成时仍显示「登录/注册」
  const showAuth = mounted && !!isAuthenticated;
  const isAdmin = mounted && !!isAuthenticated && !!(user?.is_super_admin);
  const isDark = mounted ? colorScheme === 'dark' : false;
  const displayLocale = mounted ? locale : 'zh';
  const { isOpen: authModalOpen, redirectTo, openAuthModal, closeAuthModal } = useAuthModalStore();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    if (userMenuOpen) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [userMenuOpen]);

  const displayName = user?.username || user?.email || t('common.user');
  const initials = (user?.username || user?.email || 'U').slice(0, 2).toUpperCase();

  useEffect(() => {
    return onAuthRequired((redirectTo) => {
      openAuthModal(redirectTo);
    });
  }, [openAuthModal]);

  const handleNavClick = (item: typeof NAV_ITEMS[number], e: React.MouseEvent) => {
    if (item.requiresAuth && !showAuth) {
      e.preventDefault();
      openAuthModal(item.href);
    }
    setMobileOpen(false);
  };

  const handleLoginClick = () => { openAuthModal('/explore/intro'); };
  const handleAuthModalClose = () => { closeAuthModal(); };
  const handleLogout = () => { logout(); router.push('/'); };

  const linkBase = 'px-3 py-1.5 rounded-lg text-sm transition-colors';
  const linkActive = isDark ? 'bg-white/10 text-white' : 'bg-black/5 text-black';
  const linkInactive = 'text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md';

  return (
    <>
    <nav
      className="bd-nav-glass fixed top-0 left-0 right-0 z-50 h-14"
      style={{ backgroundColor: 'var(--bd-nav-bg)', borderBottom: '1px solid var(--bd-nav-border)' }}
      suppressHydrationWarning
    >
      <div className="w-full h-full px-4 md:px-8 flex items-center justify-between relative">
        {/* 左侧：品牌 Logo（职引 / Vocation） */}
        <div className="flex items-center flex-shrink-0">
          <Link
            href="/"
            onClick={(e) => {
              e.preventDefault();
              router.push('/');
            }}
            className="relative z-[60] pointer-events-auto cursor-pointer text-lg font-bold whitespace-nowrap tracking-tight text-bd-fg"
          >
            {t('nav.brand')}
          </Link>
        </div>

        {/* 中间：导航项正中间居中 */}
        <div className="hidden md:flex absolute left-1/2 -translate-x-1/2 items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={(e) => handleNavClick(item, e)}
                className={`${linkBase} ${isActive ? linkActive : linkInactive}`}
              >
                {t(item.labelKey)}
              </Link>
            );
          })}
        </div>

        {/* 右侧：主题 / 语言 / 登录注册（靠最右） */}
        <div className="hidden md:flex justify-end items-center gap-3 flex-shrink-0">
          <select
            value={displayLocale}
            onChange={(e) => setLocale(e.target.value as 'zh' | 'en')}
            className="text-sm rounded-lg border-0 bg-transparent text-bd-muted hover:text-bd-fg cursor-pointer py-1 pr-6"
            style={{ borderColor: 'var(--bd-border)' }}
          >
            <option value="zh">中文</option>
            <option value="en">EN</option>
          </select>
          {showAuth ? (
            <div className="relative" ref={userMenuRef}>
              <button
                type="button"
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold hover:shadow-lg transition-all hover:scale-105 flex-shrink-0 overflow-hidden ring-2 ring-black/25 ring-offset-1 ring-offset-[var(--bd-nav-bg)] shadow-[0_1px_4px_rgba(0,0,0,0.2)]"
                style={{
                  background: user?.avatar_url
                    ? `url(${user.avatar_url}) center/cover`
                    : 'linear-gradient(135deg, var(--bd-phase-values), var(--bd-phase-strengths))',
                }}
                title={displayName}
              >
                {!user?.avatar_url && initials}
              </button>
              {userMenuOpen && (
                <div className="absolute right-0 mt-2 w-48 bg-bd-card border border-bd-border rounded-xl shadow-lg overflow-hidden z-50">
                  <div className="px-4 py-3 border-b border-bd-border">
                    <p className="text-sm font-medium text-bd-fg truncate">{displayName}</p>
                    {user?.email && <p className="text-xs text-bd-muted truncate">{user.email}</p>}
                  </div>
                  <Link
                    href="/dashboard"
                    onClick={() => setUserMenuOpen(false)}
                    className="block w-full px-4 py-3 text-left text-sm text-bd-fg hover:bg-bd-overlay-md transition-colors"
                  >
                    {t('nav.personalHomepage')}
                  </Link>
                  {isAdmin && (
                    <>
                      <Link
                        href="/settings/colors"
                        onClick={() => setUserMenuOpen(false)}
                        className="block w-full px-4 py-3 text-left text-sm text-bd-fg hover:bg-bd-overlay-md transition-colors"
                      >
                        {t('settings.colors')}
                      </Link>
                      <Link
                        href="/settings/style-lab"
                        onClick={() => setUserMenuOpen(false)}
                        className="block w-full px-4 py-3 text-left text-sm text-bd-fg hover:bg-bd-overlay-md transition-colors"
                      >
                        {t('settings.effects')}
                      </Link>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => { setUserMenuOpen(false); handleLogout(); }}
                    className="block w-full px-4 py-3 text-left text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                  >
                    {t('common.logout')}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              {isAdmin && (
                <Link href="/settings/colors" className="text-sm text-bd-muted hover:text-bd-fg transition-colors">
                  {t('settings.colors')}
                </Link>
              )}
              <button
                type="button"
                onClick={handleLoginClick}
                className="bd-btn-black px-4 py-1.5 rounded-lg text-sm font-medium text-white transition-colors"
              >
                {t('common.loginRegister')}
              </button>
            </>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden ml-auto p-2 text-bd-muted hover:text-bd-fg"
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div
          className="bd-nav-glass md:hidden px-4 pb-4 space-y-1"
          style={{ backgroundColor: 'var(--bd-nav-bg)', borderBottom: '1px solid var(--bd-nav-border)' }}
        >
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || (item.href !== '/' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={(e) => handleNavClick(item, e)}
                className={`block ${linkBase} ${isActive ? linkActive : linkInactive}`}
              >
                {t(item.labelKey)}
              </Link>
            );
          })}
          <div className="pt-2 border-t border-bd-border flex items-center gap-2 mb-2">
            <select
              value={displayLocale}
              onChange={(e) => setLocale(e.target.value as 'zh' | 'en')}
              className="text-sm bg-transparent text-bd-muted border-0"
            >
              <option value="zh">中文</option>
              <option value="en">EN</option>
            </select>
          </div>
          <div className="border-t border-bd-border pt-2">
            {showAuth ? (
              <>
                <Link
                  href="/dashboard"
                  onClick={() => setMobileOpen(false)}
                  className={`block ${linkBase} ${linkInactive}`}
                >
                  {t('nav.personalHomepage')}
                </Link>
                {isAdmin && (
                  <>
                    <Link
                      href="/settings/colors"
                      onClick={() => setMobileOpen(false)}
                      className={`block ${linkBase} ${linkInactive}`}
                    >
                      {t('nav.colorsMobile')}
                    </Link>
                    <Link
                      href="/settings/style-lab"
                      onClick={() => setMobileOpen(false)}
                      className={`block ${linkBase} ${linkInactive}`}
                    >
                      {t('nav.effectsMobile')}
                    </Link>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => { handleLogout(); setMobileOpen(false); }}
                  className={`block w-full text-left px-4 py-3 rounded-lg text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20`}
                >
                  {t('common.logout')}
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => { handleLoginClick(); setMobileOpen(false); }}
                className={`block w-full text-left ${linkBase} ${linkActive}`}
              >
                {t('common.loginRegister')}
              </button>
            )}
          </div>
        </div>
      )}
    </nav>

    <AuthModal isOpen={authModalOpen} onClose={handleAuthModalClose} redirectTo={redirectTo} />
  </>
  );
}
