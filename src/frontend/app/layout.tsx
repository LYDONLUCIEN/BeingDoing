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
  title: '职·引 — 不是找到方向，而是认出自己',
  description: '通过信念、禀赋、热忱与使命四个维度的深度对话，发现属于你的职业方向。',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" data-theme="ideal" data-color-scheme="light" className={`${inter.variable} ${playfair.variable}`} suppressHydrationWarning>
      <head>
        {/* Apply saved theme before first paint to avoid FOUC and hydration mismatch */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=JSON.parse(localStorage.getItem('bd-theme')||'{}');var st=s&&s.state;var cs=st&&st.colorScheme;var id=st&&st.themeId;var dark=['slate-dark'];var light=['ideal'];if(cs){document.documentElement.setAttribute('data-color-scheme',cs);document.documentElement.setAttribute('data-theme',cs==='dark'?'slate-dark':'ideal');}else if(id&&(dark.indexOf(id)>=0||light.indexOf(id)>=0)){document.documentElement.setAttribute('data-theme',id);document.documentElement.setAttribute('data-color-scheme',dark.indexOf(id)>=0?'dark':'light');}}catch(e){}})();`,
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
