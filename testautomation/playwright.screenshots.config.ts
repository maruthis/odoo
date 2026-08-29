import { defineConfig } from "@playwright/test";
import { BASE_URL } from "./src/env";

/**
 * Separate config for capturing the screenshots used in the User Guide
 * artifact (mydocs/ -> published guide). Kept apart from the other two
 * configs the same way they're kept apart from each other: this one wants
 * a fixed, consistent viewport and no video/trace overhead, and the
 * single test drives its own logins (see screenshots/capture.spec.ts)
 * rather than using per-role storageState projects.
 */
export default defineConfig({
  testDir: "./screenshots",
  timeout: 300_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  globalSetup: require.resolve("./global-setup"),

  use: {
    baseURL: BASE_URL,
    viewport: { width: 1440, height: 900 },
    trace: "off",
    video: "off",
    screenshot: "off",
  },
});
