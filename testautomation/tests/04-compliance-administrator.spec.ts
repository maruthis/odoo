/** Demo Playbook §3.4 - Compliance Administrator. */
import { expect, test } from "@playwright/test";
import { adminClient, uniqueSuffix } from "../src/seedData";
import { fieldInput, gotoComplianceMenu, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("can open Consent Purposes configuration and create one", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.configConsentPurposes);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });

  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);

  const suffix = uniqueSuffix();
  await fieldInput(page, "name").fill(`PW Admin Purpose ${suffix}`);
  await fieldInput(page, "code").fill(`PW_ADMIN_${suffix}`);
  await fieldInput(page, "privacy_notice_version").fill("v1");
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);

  await expect(page.locator(".o_form_saved, .o_form_view").first()).toBeVisible();
});

test("can open Brands configuration", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.configBrands);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });
});

test("can reinstate a suppressed contact with a reason", async ({ page }) => {
  const client = await adminClient();
  const suffix = uniqueSuffix();
  const partnerId = await client.create("res.partner", {
    name: `PW Reinstate ${suffix}`,
    email: `pw.reinstate.${suffix}@example.com`,
  });
  const [reasonId] = await client.search("newsletter.suppression.reason", [
    ["code", "=", "MANUAL"],
  ]);
  const suppressionId = await client.create("newsletter.suppression.entry", {
    partner_id: partnerId,
    scope: "global",
    reason_id: reasonId,
    source: "manual",
  });

  await page.goto(`/odoo/newsletter.suppression.entry/${suppressionId}`);
  await waitForOdooView(page);

  await page.locator('button:has-text("Reinstate")').click();
  await page.locator(".modal textarea").first().fill("Playwright: confirmed opt-back-in by phone");
  await page.locator('.modal button:has-text("Reinstate")').last().click();
  await waitForOdooView(page);

  const [suppression] = await client.callKw<any[]>("newsletter.suppression.entry", "read", [
    [suppressionId],
    ["active"],
  ]);
  expect(suppression.active).toBe(false);
});

test("Delivery & Reputation settings page opens", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.configDelivery);
  await expect(page.locator(".o_form_view")).toBeVisible({ timeout: 15000 });
  // "Newsletter Deliverability" is only the data-string used by the
  // Settings app's own sidebar navigation - this action opens the block
  // directly without that sidebar, so assert on a heading that's
  // actually rendered inside the block itself.
  await expect(page.locator("text=Reputation Policy")).toBeVisible();
});
