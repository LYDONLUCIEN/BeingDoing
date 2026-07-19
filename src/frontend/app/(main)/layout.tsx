import TopNavbar from '@/components/layout/TopNavbar';
import AuthGate from '@/components/layout/AuthGate';
import SiteNoticeBanner from '@/components/site-notices/SiteNoticeBanner';
import FloatingFeedbackWidget from '@/components/feedback/FloatingFeedbackWidget';

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="bd-aurora-bg bd-eff-bg min-h-screen bg-bd-bg" suppressHydrationWarning>
      <TopNavbar />
      <SiteNoticeBanner />
      <main className="relative pt-14">
        <AuthGate>{children}</AuthGate>
      </main>
      <FloatingFeedbackWidget />
    </div>
  );
}
