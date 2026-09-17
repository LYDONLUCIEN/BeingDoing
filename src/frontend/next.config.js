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
