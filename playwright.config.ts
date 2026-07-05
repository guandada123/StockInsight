import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  retries: 1,
  reporter: [["html", { outputFolder: "e2e-report" }], ["list"]],
  use: {
    baseURL: "http://localhost:1420",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    headless: true,
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
  webServer: [
    {
      command: "pnpm dev",
      port: 1420,
      reuseExistingServer: true,
      timeout: 30000,
    },
    {
      command: "pnpm api",
      port: 8765,
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],
});
