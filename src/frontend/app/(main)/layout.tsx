import TopNavbar from '@/components/layout/TopNavbar';

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="bd-aurora-bg bd-eff-bg min-h-screen bg-bd-bg" suppressHydrationWarning>
      <TopNavbar />
      <main className="pt-14 relative z-10">{children}</main>
    </div>
  );
}
