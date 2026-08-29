/** Demo recording - Compliance Administrator (Demo Playbook §3.4). */
import { test } from "@playwright/test";
import { adminClient, uniqueSuffix } from "../src/seedData";
import { beat, fieldInput, gotoComplianceMenu, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Compliance Administrator walkthrough", async ({ page }) => {
  const client = await adminClient();

  // Configure a new Consent Purpose.
  await gotoComplianceMenu(page, MENU.configConsentPurposes);
  await beat(page, 1500);
  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);
  const suffix = uniqueSuffix();
  await fieldInput(page, "name").fill("Product Announcements");
  await beat(page, 400);
  await fieldInput(page, "code").fill(`PRODUCT_ANNOUNCEMENTS_${suffix}`);
  await beat(page, 400);
  await fieldInput(page, "privacy_notice_version").fill("v3.2");
  await beat(page, 600);
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);
  await beat(page, 2000);

  // Brands.
  await gotoComplianceMenu(page, MENU.configBrands);
  await beat(page, 1800);

  // Reinstate a suppressed contact.
  const partnerId = await client.create("res.partner", {
    name: `Demo Reinstate Contact ${suffix}`,
    email: `demo.reinstate.${suffix}@example.com`,
  });
  const [reasonId] = await client.search("newsletter.suppression.reason", [["code", "=", "MANUAL"]]);
  const suppressionId = await client.create("newsletter.suppression.entry", {
    partner_id: partnerId,
    scope: "global",
    reason_id: reasonId,
    source: "manual",
  });
  await page.goto(`/odoo/newsletter.suppression.entry/${suppressionId}`);
  await waitForOdooView(page);
  await beat(page, 1500);
  await page.locator('button:has-text("Reinstate")').click();
  await beat(page, 600);
  await page.locator(".modal textarea").first().fill("Contact confirmed opt-back-in by phone.");
  await beat(page, 800);
  await page.locator('.modal button:has-text("Reinstate")').last().click();
  await waitForOdooView(page);
  await beat(page, 2000);

  // Delivery & Reputation settings.
  await gotoComplianceMenu(page, MENU.configDelivery);
  await beat(page, 2200);
});
