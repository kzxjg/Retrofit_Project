// Browser tests: the BUILT page (with its Content-Security-Policy) in real Chromium, talking to a
// real Django through the `vite preview` proxy, the same one-address setup as on AWS.
//
//   npx playwright install chromium   # once
//   npm run e2e
//
// Both servers are started on their own ports, so a dev server already on 8000/5173 is left alone.
import { defineConfig, devices } from '@playwright/test'

const DJANGO_PORT = 8765
const PAGE_PORT = 4765
const PYTHON = process.env.RETROFIT_PYTHON ?? '../.venv/bin/python'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'line' : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PAGE_PORT}`,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${PYTHON} ../manage.py runserver 127.0.0.1:${DJANGO_PORT} --noreload`,
      url: `http://127.0.0.1:${DJANGO_PORT}/api/health`,
      env: { DJANGO_DEBUG: '1', DJANGO_RECOMMEND_RATE_LIMIT: '1000/m' },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npm run build && npx vite preview --host 127.0.0.1 --port ${PAGE_PORT} --strictPort`,
      url: `http://127.0.0.1:${PAGE_PORT}/`,
      env: { RETROFIT_API_PROXY: `http://127.0.0.1:${DJANGO_PORT}` },
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
})
