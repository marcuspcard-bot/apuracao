import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  workers: 1,
  use: {
    baseURL: 'http://localhost:5174',
    trace: 'retain-on-failure',
    extraHTTPHeaders: { Authorization: 'Bearer isolated-test-admin-token' },
  },
  webServer: [
    {
      command:
        'cd ../backend && FRONTEND_URL=http://localhost:5174 exec .venv/bin/python -m tests.e2e_server',
      url: 'http://127.0.0.1:8001/health',
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 15000 },
    },
    {
      command:
        'VITE_API_URL=http://127.0.0.1:8001 npm run dev -- --port 5174 --strictPort',
      url: 'http://localhost:5174',
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 },
    },
  ],
})
