'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import AuthModal from './AuthModal';

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, _hasHydrated } = useAuthStore();

  const isPublic = pathname === '/';
  const needsAuth = !isPublic && _hasHydrated && !isAuthenticated;

  const handleModalClose = () => {
    router.push('/');
  };

  return (
    <>
      <div className={needsAuth ? 'pointer-events-none select-none min-h-full' : ''} style={needsAuth ? { filter: 'blur(10px)' } : undefined}>
        {children}
      </div>
      {needsAuth && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-xl">
          <AuthModal isOpen={true} onClose={handleModalClose} redirectTo={pathname} />
        </div>
      )}
    </>
  );
}
