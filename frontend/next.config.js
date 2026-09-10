/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  outputFileTracingRoot: __dirname,
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ['@radix-ui/react-icons', '@radix-ui/react-select'],
  },
};

module.exports = nextConfig;
