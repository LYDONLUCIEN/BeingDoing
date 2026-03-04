import type { Metadata } from 'next';
import { Inter, Playfair_Display } from 'next/font/google';
import './globals.css';
import ThemeProvider from '@/components/layout/ThemeProvider';
import PhaseColorInjector from '@/components/layout/PhaseColorInjector';
import DesignEffectsInjector from '@/components/layout/DesignEffectsInjector';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

const playfair = Playfair_Display({
  subsets: ['latin'],
  variable: '--font-playfair',
  display: 'swap',
  weight: ['400', '600', '700'],
  style: ['normal', 'italic'],
});

export const metadata: Metadata = {
  title: 'Being · Doing — 每一种热爱，都值得成为职业',
  description: '通过信念、禀赋、热忱与使命四个维度的深度对话，发现属于你的职业方向。',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" data-theme="slate-dark" className={`${inter.variable} ${playfair.variable}`} suppressHydrationWarning>
      <head>
        {/* Apply saved theme before first paint to avoid FOUC and hydration mismatch */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=JSON.parse(localStorage.getItem('bd-theme')||'{}');var id=t&&t.state&&t.state.themeId;if(id)document.documentElement.setAttribute('data-theme',id);}catch(e){}})();`,
          }}
        />
      </head>
      <body className={inter.className} suppressHydrationWarning>
        <ThemeProvider />
        <PhaseColorInjector />
        <DesignEffectsInjector />
        {children}
      </body>
    </html>
  );
}
