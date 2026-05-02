import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';
import Providers from '@/components/layout/Providers';

const inter = localFont({
  src: '../public/fonts/Inter-Variable.ttf',
  variable: '--font-inter',
  display: 'swap',
});

const playfair = localFont({
  src: [
    { path: '../public/fonts/PlayfairDisplay-Variable.ttf', style: 'normal' },
    { path: '../public/fonts/PlayfairDisplay-Italic-Variable.ttf', style: 'italic' },
  ],
  variable: '--font-playfair',
  display: 'swap',
});

const notoSansSC = localFont({
  src: [
    { path: '../public/fonts/NotoSansSC-Light.woff2', weight: '300', style: 'normal' },
    { path: '../public/fonts/NotoSansSC-Regular.woff2', weight: '400', style: 'normal' },
    { path: '../public/fonts/NotoSansSC-Medium.woff2', weight: '500', style: 'normal' },
    { path: '../public/fonts/NotoSansSC-SemiBold.woff2', weight: '600', style: 'normal' },
  ],
  variable: '--font-noto-sans-sc',
  display: 'swap',
});

const notoSerifSC = localFont({
  src: [
    { path: '../public/fonts/NotoSerifSC-Regular.woff2', weight: '400', style: 'normal' },
    { path: '../public/fonts/NotoSerifSC-SemiBold.woff2', weight: '600', style: 'normal' },
  ],
  variable: '--font-noto-serif-sc',
  display: 'swap',
});

export const metadata: Metadata = {
  title: '职引 — 不是找到方向，而是认出自己',
  description: '通过信念、禀赋、热忱与使命四个维度的深度对话，发现属于你的职业方向。',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" data-theme="ideal" data-color-scheme="light" className={`${inter.variable} ${playfair.variable} ${notoSansSC.variable} ${notoSerifSC.variable}`} suppressHydrationWarning>
      <head>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/lxgw-wenkai-lite-webfont@1.1.0/style.css" />
        {/* Apply saved theme before first paint to avoid FOUC and hydration mismatch */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=JSON.parse(localStorage.getItem('bd-theme')||'{}');var st=s&&s.state;var cs=st&&st.colorScheme;var id=st&&st.themeId;var dark=['slate-dark'];var light=['ideal'];if(cs){document.documentElement.setAttribute('data-color-scheme',cs);document.documentElement.setAttribute('data-theme',cs==='dark'?'slate-dark':'ideal');}else if(id&&(dark.indexOf(id)>=0||light.indexOf(id)>=0)){document.documentElement.setAttribute('data-theme',id);document.documentElement.setAttribute('data-color-scheme',dark.indexOf(id)>=0?'dark':'light');}}catch(e){}})();`,
          }}
        />
      </head>
      <body className={inter.className} style={{ fontFamily: 'var(--font-sans-cn)' }} suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
