/** Demo recording - Legal Hold Administrator (Demo Playbook §3.8). */
import { test } from "@playwright/test";
import { adminClient, uniqueSuffix } from "../src/seedData";
import { beat, fieldInput, gotoComplianceMenu, selectDropdownOption, statusbarOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Legal Hold Administrator walkthrough", async ({ page }) => {
  const client = await adminClient();
  const suffix = uniqueSuffix();

  // Create a company-wide legal hold.
  await gotoComplianceMenu(page, MENU.legalHolds);
  await beat(page, 1500);
  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);

  await fieldInput(page, "name").fill(`Demo Legal Hold ${suffix}`);
  await beat(page, 400);
  await fieldInput(page, "reason").fill("Litigation preservation demo.");
  await beat(page, 400);
  await selectDropdownOption(page, "scope_type", "Entire Company");
  await beat(page, 600);
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);
  await statusbarOption(page, "status", "active").waitFor({ state: "visible" });
  await beat(page, 2000);

  // Release it immediately from the form.
  await page.locator('button:has-text("Release Hold")').click();
  await beat(page, 600);
  await page.locator(".modal textarea").first().fill("Investigation closed.");
  await beat(page, 800);
  await page.locator('.modal button:has-text("Release Hold")').last().click();
  await waitForOdooView(page);
  await statusbarOption(page, "status", "released").waitFor({ state: "visible" });
  await beat(page, 2200);

  // Retention Action Ledger.
  await gotoComplianceMenu(page, MENU.retentionActionLedger);
  await beat(page, 1800);
});
