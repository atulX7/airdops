/** @type {import('next').NextConfig} */
const path = require('path')

const nextConfig = {
  output: 'standalone',
  images: {
    domains: ['localhost'],
  },
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
  },
  webpack: (config) => {
    if (!config.resolve) {
      config.resolve = {}
    }
    if (!config.resolve.alias) {
      config.resolve.alias = {}
    }
    config.resolve.alias['@'] = path.resolve(__dirname, '.')
    config.resolve.alias['next-auth/react'] = path.resolve(__dirname, 'lib/next-auth-react.tsx')
    return config
  },
}

module.exports = nextConfig
