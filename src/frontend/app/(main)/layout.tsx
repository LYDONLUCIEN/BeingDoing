import TopNavbar from '@/components/layout/TopNavbar';

export default function MainLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <TopNavbar />
      <main className="pt-14">{children}</main>
    </>
  );
}
