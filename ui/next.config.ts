/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    appDir: true,
  },
  output: 'standalone',
  images: {
    domains: ['localhost'],
  },
  env: {
    // API URL is now centralized in lib/config.ts
    // Keep NEXT_PUBLIC_API_BASE for build-time environment variable injection if needed
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
    NEXT_PUBLIC_AIRFLOW_URL: process.env.NEXT_PUBLIC_AIRFLOW_URL || 'http://localhost:8080',
  },
}

module.exports = nextConfig
