'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useAuthModalStore } from '@/stores/authModalStore';
import { useThemeStore, DARK_THEMES } from '@/stores/themeStore';
import { useLocaleStore } from '@/stores/localeStore';
import { onAuthRequired } from '@/lib/api/client';
import { NAV_ITEMS } from '@/lib/nav';
import { useLocale } from '@/hooks/useLocale';
import { useState, useEffect } from 'react';
import { Menu, X, Sun, Moon } from 'lucide-react';
import AuthModal from './AuthModal';

export default function TopNavbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useLocale();
  const { isAuthenticated, user, logout, _hasHydrated } = useAuthStore();
  const { themeId, toggleColorScheme } = useThemeStore();
  const isDark = DARK_THEMES.includes(themeId);
  const { locale, setLocale } = useLocaleStore();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  // 仅挂载后根据 persist 状态渲染登录态，确保服务端与客户端首帧一致，避免 Hydration Error
  const showAuth = mounted && _hasHydrated ? isAuthenticated : false;
  const { isOpen: authModalOpen, redirectTo, openAuthModal, closeAuthModal } = useAuthModalStore();

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

  const handleLoginClick = () => { openAuthModal('/explore'); };
  const handleAuthModalClose = () => { closeAuthModal(); };
  const handleLogout = () => { logout(); router.push('/'); };

  const linkBase = 'px-3 py-1.5 rounded-lg text-sm transition-colors';
  const linkActive = 'bg-bd-ui-accent-dim text-bd-ui-accent';
  const linkInactive = 'text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md';

  return (
    <>
    <nav
      className="bd-nav-glass fixed top-0 left-0 right-0 z-50 h-14"
      style={{ backgroundColor: 'var(--bd-nav-bg)', borderBottom: '1px solid var(--bd-nav-border)' }}
    >
      <div className="max-w-7xl mx-auto h-full px-4 flex items-center justify-between">
        {/* Brand */}
        <Link href="/" className="text-lg font-bold whitespace-nowrap tracking-tight text-bd-fg">
          {t('nav.brand')}
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-1">
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

        {/* Right side: theme toggle, lang, auth */}
        <div className="hidden md:flex items-center gap-3">
          <button
            type="button"
            onClick={toggleColorScheme}
            className="p-2 rounded-lg text-bd-muted hover:text-bd-fg hover:bg-bd-overlay transition-colors"
            title={isDark ? '切换到浅色' : '切换到深色'}
            aria-label={isDark ? 'Switch to light' : 'Switch to dark'}
          >
            {isDark ? <Moon size={18} /> : <Sun size={18} />}
          </button>
          <select
            value={locale}
            onChange={(e) => setLocale(e.target.value as 'zh' | 'en')}
            className="text-sm rounded-lg border-0 bg-transparent text-bd-muted hover:text-bd-fg cursor-pointer py-1 pr-6"
            style={{ borderColor: 'var(--bd-border)' }}
          >
            <option value="zh">中文</option>
            <option value="en">EN</option>
          </select>
          {showAuth ? (
            <>
              <Link
                href="/settings/colors"
                className="text-sm text-bd-muted hover:text-bd-fg transition-colors"
              >
                {t('settings.colors')}
              </Link>
              <Link
                href="/settings/style-lab"
                className="text-sm text-bd-muted hover:text-bd-fg transition-colors"
              >
                {t('settings.effects')}
              </Link>
              <span className="text-sm text-bd-muted">
                {user?.username || user?.email || t('common.user')}
              </span>
              <button
                type="button"
                onClick={handleLogout}
                className={`${linkBase} ${linkInactive}`}
              >
                {t('common.logout')}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={handleLoginClick}
              className="px-4 py-1.5 rounded-lg text-sm font-medium text-bd-ui-accent-fg transition-colors hover:opacity-90"
              style={{ background: 'var(--bd-ui-accent)' }}
            >
              {t('common.loginRegister')}
            </button>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden p-2 text-bd-muted hover:text-bd-fg"
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
            <button
              type="button"
              onClick={toggleColorScheme}
              className="p-2 rounded-lg text-bd-muted hover:text-bd-fg"
            >
              {isDark ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <select
              value={locale}
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
                <button
                  type="button"
                  onClick={() => { handleLogout(); setMobileOpen(false); }}
                  className={`block w-full text-left ${linkBase} ${linkInactive}`}
                >
                  {t('nav.logoutUserTemplate', { name: user?.username || user?.email || t('common.user') })}
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
