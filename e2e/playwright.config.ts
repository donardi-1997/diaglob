import { defineConfig, devices } from "@playwright/test";

const stagingOnly = process.env.E2E_STAGING_ONLY === "1";
const stagingBase = process.env.E2E_STAGING_BASE_URL?.trim();
const mockBase = "http://127.0.0.1:4173";

if (stagingOnly) {
  if (!stagingBase || process.env.E2E_STAGING_READONLY_ACK !== "yes") {
    throw new Error("Staging tests require a staging URL and explicit read-only acknowledgement.");
  }
  const url = new URL(stagingBase);
  const host = url.hostname.toLowerCase();
  // Fail closed: a typo cannot turn a reviewer smoke test into a production probe.
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash ||
      url.pathname !== "/" || url.port ||
      !(host === "staging.diaglob.tech" || host.endsWith(".staging.diaglob.tech"))) {
    throw new Error("Only HTTPS hosts in the staging.diaglob.tech zone are allowed.");
  }
}

export default defineConfig({
  testDir: "./tests",
  testMatch: stagingOnly ? "**/*.staging.spec.ts" : "**/*.mock.spec.ts",
  fullyParallel: !stagingOnly,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  retries: stagingOnly ? 0 : process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: stagingOnly
    ? [["line"]]
    : [["line"], ["junit", { outputFile: "test-results/junit.xml" }],
       ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: stagingOnly ? stagingBase : mockBase,
    trace: stagingOnly ? "off" : "retain-on-failure",
    screenshot: stagingOnly ? "off" : "only-on-failure",
    video: "off",
  },
  projects: [{
    name: stagingOnly ? "chromium-staging-readonly" : "chromium-mocked",
    use: { ...devices["Desktop Chrome"] },
  }],
  webServer: stagingOnly ? undefined : {
    command: "npm --prefix ../frontend run dev -- --host 127.0.0.1 --port 4173 --strictPort",
    url: mockBase + "/login",
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
    env: { VITE_API_URL: mockBase },
  },
});
