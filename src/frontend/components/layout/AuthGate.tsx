'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useAuthModalStore } from '@/stores/authModalStore';
import { authApi } from '@/lib/api/auth';

/**
 * 无需登录即可访问的公开页面。
 * 隐私声明 / 用户协议是首页弹窗（LegalDocModal），随首页公开；
 * /auth/login、/auth/register、/account-recovery 在 (main) 组之外，本就不经过 AuthGate。
 */
const PUBLIC_PATHS = new Set(['/', '/about', '/community', '/verify-email']);

/**
 * 会话级一次性 token 校验：
 * localStorage 里的登录态不代表 token 仍有效（服务重启 / token 过期）。
 * 每次页面加载（SPA 会话）校验一次 /auth/me；若 401 且 refresh 失败，
 * axios 拦截器会统一 logout + 发 auth:required 事件，AuthGate 随之退回首页。
 */
let sessionValidated = false;

function validateSessionOnce(): void {
  if (sessionValidated) return;
  sessionValidated = true;
  authApi.getCurrentUser().catch(() => {
    // 401 已由响应拦截器统一处理（logout + auth:required）；其他错误不打扰用户
  });
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, _hasHydrated, recoveryMode } = useAuthStore();
  const openAuthModal = useAuthModalStore((s) => s.openAuthModal);

  const isPublic = PUBLIC_PATHS.has(pathname);
  const needsAuth = !isPublic && _hasHydrated && !isAuthenticated;
  // 账户恢复会话（受限 token）：只允许停留在恢复页，且跳过 /auth/me 校验
  // （受限 token 调 /auth/me 必 401，会触发拦截器误登出）
  const needsRecovery = _hasHydrated && isAuthenticated && recoveryMode;

  useEffect(() => {
    if (needsRecovery) {
      router.replace('/account-recovery');
      return;
    }
    if (needsAuth) {
      // 未登录访问受保护页面（激活码 / 5 个 phase / 报告 / dashboard 等）：
      // 直接退回首页并弹出登录框，登录成功后停留在首页
      router.replace('/');
      openAuthModal('/');
      return;
    }
    if (_hasHydrated && isAuthenticated && !recoveryMode) {
      validateSessionOnce();
    }
  }, [needsAuth, needsRecovery, _hasHydrated, isAuthenticated, recoveryMode, router, openAuthModal]);

  // 未登录时不渲染受保护内容，避免内容闪现和触发带缓存的 API 请求
  if (needsAuth) return null;
  // 恢复会话不渲染主站内容，等待跳转到恢复页
  if (needsRecovery) return null;

  return <>{children}</>;
}
