/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 允许从外部域名访问 dev 资源，避免 503（Next.js 开发模式安全限制）
  allowedDevOrigins: [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'https://career.soulhappylab.com',
    'http://career.soulhappylab.com',
    'http://47.96.75.69:3000',
    'http://47.96.75.69',
  ],
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
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
