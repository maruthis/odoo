import { defineConfig, devices } from "@playwright/test";
import path from "path";
import { BASE_URL } from "./src/env";

const AUTH_DIR = path.join(__dirname, ".auth");

/**
 * Separate config for recording demo videos (npm run demo). Kept apart
 * from playwright.config.ts on purpose - the main suite is tuned for
 * fast, reliable assertions, this one is tuned for a single continuous,
 * watchable video per role. Reuses the same global-setup (demo users +
 * auth states) as the real test suite.
 */
export default defineConfig({
  testDir: "./demo",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { outputFolder: "./demo-recordings/report", open: "never" }]],
  globalSetup: require.resolve("./global-setup"),
  outputDir: "./demo-recordings/.raw",

  use: {
    baseURL: BASE_URL,
    viewport: { width: 1600, height: 1000 },
    video: { mode: "on", size: { width: 1600, height: 1000 } },
    trace: "off",
    screenshot: "off",
  },

  projects: [
    // No storageState - this test starts logged out and drives every
    // login itself (see nav.ts's loginAs/switchUser), since it stays on
    // one continuous page/video across all 9 roles.
    { name: "00-full-platform-e2e", testMatch: "00-full-platform-e2e.demo.ts" },
    { name: "01-author", testMatch: "01-author.demo.ts", use: { storageState: path.join(AUTH_DIR, "author.json") } },
    { name: "02-content-approver", testMatch: "02-content-approver.demo.ts", use: { storageState: path.join(AUTH_DIR, "contentApprover.json") } },
    { name: "03-compliance-reviewer", testMatch: "03-compliance-reviewer.demo.ts", use: { storageState: path.join(AUTH_DIR, "complianceReviewer.json") } },
    { name: "04-compliance-administrator", testMatch: "04-compliance-administrator.demo.ts", use: { storageState: path.join(AUTH_DIR, "complianceAdmin.json") } },
    { name: "05-campaign-operator", testMatch: "05-campaign-operator.demo.ts", use: { storageState: path.join(AUTH_DIR, "operator.json") } },
    { name: "06-operations-administrator", testMatch: "06-operations-administrator.demo.ts", use: { storageState: path.join(AUTH_DIR, "opsAdmin.json") } },
    { name: "07-privacy-officer", testMatch: "07-privacy-officer.demo.ts", use: { storageState: path.join(AUTH_DIR, "privacyOfficer.json") } },
    { name: "08-legal-hold-administrator", testMatch: "08-legal-hold-administrator.demo.ts", use: { storageState: path.join(AUTH_DIR, "legalHoldAdmin.json") } },
    { name: "09-compliance-audit-reviewer", testMatch: "09-compliance-audit-reviewer.demo.ts", use: { storageState: path.join(AUTH_DIR, "auditor.json") } },
  ],
});
