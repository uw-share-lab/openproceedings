import { defineConfig, devices } from "@playwright/test";

const root = "..";
// 8000 and 3000 unless the environment says otherwise (the fixture server reads the same two), so a run can
// sit beside an instance already on them
const apiPort = Number(process.env.OP_E2E_API_PORT ?? "8000");
const webPort = Number(process.env.OP_E2E_WEB_PORT ?? "3000");

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
    baseURL: `http://127.0.0.1:${webPort}`,
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
      url: `http://127.0.0.1:${apiPort}/api/v1/healthz`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npm run build --workspace frontend && npm run start --workspace frontend",
      cwd: root,
      env: {
        ...process.env,
        HOSTNAME: "127.0.0.1",
        PORT: String(webPort),
        NEXT_PUBLIC_API_BASE_URL: `http://127.0.0.1:${apiPort}`,
        // A placeholder (RFC 2606 domain): e2e checks the footer names the configured contact.
        NEXT_PUBLIC_TAKEDOWN_CONTACT: "takedown@example.org",
        NEXT_TELEMETRY_DISABLED: "1",
      },
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
