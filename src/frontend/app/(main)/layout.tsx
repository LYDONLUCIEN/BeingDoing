import dynamic from 'next/dynamic';
import AuthGate from '@/components/layout/AuthGate';

const TopNavbar = dynamic(() => import('@/components/layout/TopNavbar'), { ssr: false });

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="bd-aurora-bg bd-eff-bg min-h-screen bg-bd-bg" suppressHydrationWarning>
      <TopNavbar />
      <main className="pt-14 relative z-10">
        <AuthGate>{children}</AuthGate>
      </main>
    </div>
  );
}
