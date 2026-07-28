import AuthGate from '@/components/layout/AuthGate';

/**
 * /profile/* 在 (main) 组之外，不经过 (main)/layout 的 AuthGate，
 * 这里单独包一层，保证未登录访问时统一退回首页并弹登录框。
 */
export default function ProfileLayout({ children }: { children: React.ReactNode }) {
  return <AuthGate>{children}</AuthGate>;
}
