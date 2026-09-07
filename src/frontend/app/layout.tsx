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
  title: '寻路·OpenLife — 所有热爱,都值得成为事业',
  description: '通过价值观、优势、热爱与使命四个维度的深度对话，发现属于你的职业方向。',
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
        {/* IE / 极老内核兑底（ADR-0020）：React bundle 在这些环境根本跑不起来，
            只能用 ES5 内联脚本画静态提示层。IE 条件注释 + documentMode + Promise 三重检测；
            正常现代浏览器此脚本为空操作。 */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var isIE=/*@cc_on!@*/false||!!document.documentMode;var noPromise=typeof Promise==='undefined';if(!isIE&&!noPromise)return;var show=function(){if(document.getElementById('bd-legacy-ie-notice'))return;var d=document.createElement('div');d.id='bd-legacy-ie-notice';d.style.cssText='position:fixed;top:0;left:0;right:0;bottom:0;z-index:2147483647;background:#fafaf7;padding:15vh 24px 24px;text-align:center;font-family:system-ui,sans-serif;color:#44403c;';d.innerHTML='<div style="max-width:420px;margin:0 auto"><div style="font-size:18px;font-weight:600;margin-bottom:12px">浏览器版本过旧</div><div style="font-size:14px;line-height:1.9">当前浏览器（或 IE 兼容模式）版本过旧，页面无法正常显示。<br>请切换到浏览器的「高速模式」，或使用最新版 Microsoft Edge / Google Chrome 访问。</div></div>';document.body.appendChild(d);};if(document.body){show();}else if(document.addEventListener){document.addEventListener('DOMContentLoaded',show);}else if(window.attachEvent){window.attachEvent('onload',show);}})();`,
          }}
        />
      </head>
      <body className={inter.className} style={{ fontFamily: 'var(--font-sans-cn)' }} suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
