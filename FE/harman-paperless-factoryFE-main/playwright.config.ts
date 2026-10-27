import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests against a running system: the Vite dev server (proxying /api)
 * and the backend with the seeded demo data.
 *
 *   BE:  python cli.py init && python scripts/seed_quality_records.py && python cli.py serve
 *   FE:  npm run dev
 *   run: npm run test:e2e
 *
 * The suites change data (they file records, raise requests); re-seed afterwards.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1, // the suites build on each other's data, in file order
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
