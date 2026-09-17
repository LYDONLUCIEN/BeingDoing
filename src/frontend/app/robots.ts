import type { MetadataRoute } from 'next';

// 站点唯一正主域名（canonical host）。生产环境必须显式配置 NEXT_PUBLIC_SITE_URL。
// 非生产（缺省/test/dev）一律全站 Disallow，保证测试环境永远不会被搜索引擎收录。
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || '';
const PROD_SITE_URL = 'https://openlife.beyondego.me';
const IS_PROD = SITE_URL === PROD_SITE_URL;

export default function robots(): MetadataRoute.Robots {
  if (!IS_PROD) {
    // 测试/dev 环境：禁止一切抓取（career.beyondego.me 另有 Basic Auth + X-Robots-Tag 双保险）
    return {
      rules: { userAgent: '*', disallow: '/' },
    };
  }
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: ['/api/', '/admin', '/dashboard', '/auth', '/profile', '/payment', '/explore'],
    },
    sitemap: `${PROD_SITE_URL}/sitemap.xml`,
  };
}
