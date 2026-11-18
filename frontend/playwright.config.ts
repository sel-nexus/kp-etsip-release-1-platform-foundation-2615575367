import { defineConfig } from '@playwright/test';
import { randomBytes } from 'node:crypto';

// Require an explicit, disposable database; never fall back to backend/.env.
const mongoUri = process.env.E2E_MONGODB_URI;
const mongoDb = process.env.E2E_MONGODB_DB;
if (!mongoUri || !mongoDb || !/^ketsip_e2e_[a-z0-9_]+$/.test(mongoDb) || process.env.E2E_DISPOSABLE_DB !== mongoDb) {
  throw new Error('Set E2E_MONGODB_URI, a disposable E2E_MONGODB_DB named ketsip_e2e_..., and E2E_DISPOSABLE_DB equal to that name.');
}

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  // The identity journey changes the seeded administrator's initial password.
  projects: [
    { name: 'initial-identity', testMatch: /auth\.spec\.ts/ },
    { name: 'journeys', testIgnore: /auth\.spec\.ts/, dependencies: ['initial-identity'] },
  ],
  use: { baseURL: 'http://127.0.0.1:5173', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: [
    {
      command: 'cd ../backend && ${E2E_PYTHON:-python3} -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
      env: {
        MONGODB_URI: mongoUri,
        MONGODB_DB: mongoDb,
        SEED_ON_STARTUP: 'true',
        SEED_PASSWORD: process.env.E2E_INITIAL_PASSWORD || 'DemoPassword123!',
        JWT_SECRET: randomBytes(32).toString('hex'),
      },
      timeout: 120_000,
    },
    {
      command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      env: { VITE_PROXY_TARGET: 'http://127.0.0.1:8000', VITE_API_BASE: '/api' },
      timeout: 120_000,
    },
  ],
});
