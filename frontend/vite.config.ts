import react from '@vitejs/plugin-react'
import { loadEnv, type Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

// Content-Security-Policy for the built page: only this site's own scripts, styles, fonts and images
// may load. It is added at build time only, because the dev server injects inline scripts for hot
// reload that a strict policy would block. On AWS, send the same policy as a CloudFront header too
// (a <meta> policy cannot set frame-ancestors).
function contentSecurityPolicy(apiUrl: string): Plugin {
  const connect = ["'self'"]
  if (apiUrl) connect.push(new URL(apiUrl).origin)
  const policy = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "font-src 'self'",
    "img-src 'self' data:",
    `connect-src ${connect.join(' ')}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
  return {
    name: 'content-security-policy',
    apply: 'build',
    transformIndexHtml: () => [
      { tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: policy }, injectTo: 'head-prepend' },
    ],
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), contentSecurityPolicy(loadEnv(mode, process.cwd(), 'VITE_').VITE_API_URL ?? '')],
  server: {
    // Forward /api calls to Django so the browser never needs CORS during development.
    // changeOrigin must stay false (the string shorthand turns it on): Django's CSRF check compares
    // the browser's Origin (http://localhost:5173) with the Host header, so the Host must not be
    // rewritten to 127.0.0.1:8000, or every POST gets 403 "Origin checking failed".
    // `vite preview` uses the same proxy. RETROFIT_API_PROXY lets the browser tests (e2e/) point it
    // at their own Django on another port.
    proxy: {
      '/api': { target: process.env.RETROFIT_API_PROXY ?? 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'], // e2e/ is for Playwright (npm run e2e), not Vitest
    // Loads the jest-dom matchers and unmounts rendered components after each test.
    setupFiles: ['./src/setupTests.ts'],
  },
}))
