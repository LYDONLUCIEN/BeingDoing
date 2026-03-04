import TopNavbar from '@/components/layout/TopNavbar';

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    /* bd-aurora-bg applies the animated mesh gradient when [data-theme="aurora"] is active.
       On other themes this class has no effect. */
    <div className="bd-aurora-bg bd-eff-bg min-h-screen bg-bd-bg" suppressHydrationWarning>
      <TopNavbar />
      <main className="pt-14 relative z-10">{children}</main>
    </div>
  );
}
