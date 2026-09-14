import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",

  // One worker against one shared server process. Parallelism here would buy
  // seconds on a five-test suite and cost cross-test interference, which is
  // the failure mode this suite cannot afford.
  fullyParallel: false,
  workers: 1,

  // Zero, permanently. A retry budget is the mechanism by which a required
  // gate becomes decoration: the first flaky red becomes a re-run, and once
  // re-running is routine the gate consumes attention and pays nothing. A
  // flaky test here is a defective test — delete it, do not retry it.
  retries: 0,

  forbidOnly: !!process.env.CI,
  globalSetup: "./tests/browser/globalSetup.ts",
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],

  use: {
    trace: "retain-on-failure",
  },

  // Chromium only. The three defects are layout and hit-testing bugs in the
  // engine the app is developed against; a second engine multiplies install
  // time and flake surface for coverage nobody asked for.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
