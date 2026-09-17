import type { MetadataRoute } from 'next';

// 仅生产环境输出真实 sitemap；非生产返回空表（配合 robots.ts 的 Disallow 双保险）。
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || '';
const PROD_SITE_URL = 'https://openlife.beyondego.me';
const IS_PROD = SITE_URL === PROD_SITE_URL;

export default function sitemap(): MetadataRoute.Sitemap {
  if (!IS_PROD) return [];
  const now = new Date();
  return [
    {
      url: PROD_SITE_URL,
      lastModified: now,
      changeFrequency: 'weekly',
      priority: 1,
    },
  ];
}
