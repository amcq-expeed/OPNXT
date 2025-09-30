/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'export',
  trailingSlash: true,
  async rewrites() {
    return [
      { source: '/favicon.ico', destination: '/opnxt-logo.svg' },
    ];
  },
};

export default nextConfig;
