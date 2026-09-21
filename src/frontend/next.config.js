/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 允许从外部域名访问 dev 资源，避免 503（Next.js 开发模式安全限制）
  allowedDevOrigins: [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'https://career.soulhappylab.com',
    'http://career.soulhappylab.com',
    // 双域名并存：beyondego.me 与 soulhappylab.com 同时可用
    'https://career.beyondego.me',
    'http://career.beyondego.me',
    // 注意：禁止在此添加裸 IP（如 http://x.x.x.x:3000）——服务已绑定 127.0.0.1，
    // 裸 IP 访问已被安全组 + localhost 绑定双重封死，加了也访问不到，只会误导。
  ],
  // 静态资源缓存口径（2026-09-21）：public/ 下文件名不带哈希，
  // 统一要求引用时带 ?v= 版本号（更新资源时递增版本号即击穿缓存）。
  // nginx 层有同口径的 location 规则（见 deploy/ 与 wiki/开发文档/0705-nginx.md），
  // 这里的 headers 是直连 Next（dev/排障）时的兜底，两层保持一致。
  async headers() {
    const longCache = {
      key: 'Cache-Control',
      value: 'public, max-age=2592000, immutable',
    };
    return [
      { source: '/assets/:path*', headers: [longCache] },
      { source: '/fonts/:path*', headers: [longCache] },
    ];
  },
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    if (!apiUrl) return [];
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
