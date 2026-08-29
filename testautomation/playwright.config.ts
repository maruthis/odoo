import { defineConfig, devices } from "@playwright/test";
import path from "path";
import { BASE_URL } from "./src/env";

const AUTH_DIR = path.join(__dirname, ".auth");

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // shared Odoo DB/session state - safer sequential by default
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : 1,
  reporter: [["list"], ["html", { open: "never" }]],
  globalSetup: require.resolve("./global-setup"),

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "public",
      testMatch: "00-public/**/*.spec.ts",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "author",
      testMatch: "01-newsletter-author.spec.ts",
      use: { ...devices["Desktop Chrome"], storageState: path.join(AUTH_DIR, "author.json") },
    },
    {
      name: "contentApprover",
      testMatch: "02-content-approver.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        storageState: path.join(AUTH_DIR, "contentApprover.json"),
      },
    },
    {
      name: "complianceReviewer",
      testMatch: "03-compliance-reviewer.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        storageState: path.join(AUTH_DIR, "complianceReviewer.json"),
      },
    },
    {
      name: "complianceAdmin",
      testMatch: "04-compliance-administrator.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        storageState: path.join(AUTH_DIR, "complianceAdmin.json"),
      },
    },
    {
      name: "operator",
      testMatch: "05-campaign-operator.spec.ts",
      use: { ...devices["Desktop Chrome"], storageState: path.join(AUTH_DIR, "operator.json") },
    },
    {
      name: "opsAdmin",
      testMatch: "06-operations-administrator.spec.ts",
      use: { ...devices["Desktop Chrome"], storageState: path.join(AUTH_DIR, "opsAdmin.json") },
    },
    {
      name: "privacyOfficer",
      testMatch: "07-privacy-officer.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        storageState: path.join(AUTH_DIR, "privacyOfficer.json"),
      },
    },
    {
      name: "legalHoldAdmin",
      testMatch: "08-legal-hold-administrator.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        storageState: path.join(AUTH_DIR, "legalHoldAdmin.json"),
      },
    },
    {
      name: "auditor",
      testMatch: "09-compliance-audit-reviewer.spec.ts",
      use: { ...devices["Desktop Chrome"], storageState: path.join(AUTH_DIR, "auditor.json") },
    },
    {
      name: "lifecycle",
      testMatch: "10-end-to-end-lifecycle.spec.ts",
      use: { ...devices["Desktop Chrome"] }, // this spec switches contexts/storage state per role itself
    },
  ],
});
