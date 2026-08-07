import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'standalone', // 阶段 6：Docker 多阶段构建产物（独立 Node 服务）
  // outputFileTracingRoot: path.resolve(__dirname, '../../'),  // Uncomment and add 'import path from "path"' if needed
  /* config options here */
  allowedDevOrigins: ['*.dev.coze.site'],
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '*',
        pathname: '/**',
      },
    ],
  },
};

export default nextConfig;
