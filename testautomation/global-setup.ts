import { chromium, type FullConfig } from "@playwright/test";
import path from "path";
import { ADMIN_LOGIN, ADMIN_PASSWORD, BASE_URL, DEMO_PASSWORD, ROLES } from "./src/env";
import { ensureDemoUsers } from "./src/seedUsers";

const AUTH_DIR = path.join(__dirname, ".auth");

async function loginAndSaveState(login: string, password: string, outFile: string) {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(`${BASE_URL}/web/login`);
  await page.fill("#login", login);
  await page.fill("#password", password);
  await page.click('button:has-text("Log in")');
  // A successful login redirects to /odoo/...; staying on /web/login means
  // the credentials were rejected - fail loudly rather than saving a
  // logged-out storage state that would make every downstream test fail
  // with a confusing "menu not found" error instead.
  await page.waitForURL(/\/odoo(\/|$)/, { timeout: 20000 });
  await page.context().storageState({ path: outFile });
  await browser.close();
}

export default async function globalSetup(_config: FullConfig) {
  await ensureDemoUsers();

  await loginAndSaveState(ADMIN_LOGIN, ADMIN_PASSWORD, path.join(AUTH_DIR, "admin.json"));

  for (const role of ROLES) {
    await loginAndSaveState(role.login, DEMO_PASSWORD, path.join(AUTH_DIR, `${role.key}.json`));
  }
}
