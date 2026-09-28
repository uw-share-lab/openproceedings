import { defineConfig, devices } from "@playwright/test";

const root = "..";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  snapshotDir: "./e2e/__screenshots__",
  snapshotPathTemplate: "{snapshotDir}/{testFileName}-snapshots/{arg}-{platform}{ext}",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  expect: {
    timeout: 15_000,
    toHaveScreenshot: { animations: "disabled", maxDiffPixelRatio: 0.02, threshold: 0.3 },
  },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:3000",
    locale: "en-US",
    timezoneId: "UTC",
    colorScheme: "light",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command:
        "PYTHONPATH=backend UV_CACHE_DIR=/tmp/openproceedings-uv-cache uv run python -m tests.e2e.fixture_server",
      cwd: root,
      url: "http://127.0.0.1:8000/api/v1/healthz",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npm run build --workspace frontend && npm run start --workspace frontend",
      cwd: root,
      env: {
        ...process.env,
        HOSTNAME: "127.0.0.1",
        PORT: "3000",
        NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
        NEXT_TELEMETRY_DISABLED: "1",
      },
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
