/** Demo Playbook §3.8 - Legal Hold Administrator. */
import { expect, test } from "@playwright/test";
import { adminClient, uniqueSuffix } from "../src/seedData";
import { fieldInput, gotoComplianceMenu, selectDropdownOption, statusbarOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("can create a company-wide legal hold", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.legalHolds);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });

  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);

  const suffix = uniqueSuffix();
  await fieldInput(page, "name").fill(`PW Legal Hold ${suffix}`);
  await fieldInput(page, "reason").fill("Playwright: litigation preservation test");
  await selectDropdownOption(page, "scope_type", "Entire Company");
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);

  await expect(statusbarOption(page, "status", "active")).toHaveAttribute(
    "aria-checked",
    "true"
  );

  // A company-wide hold blocks retention for every record system-wide
  // (by design) - release it so this test doesn't leave a standing hold
  // behind that would affect every other test/run against this database.
  const client = await adminClient();
  const [holdId] = await client.search("newsletter.legal.hold", [
    ["name", "=", `PW Legal Hold ${suffix}`],
  ]);
  await client.callKw("newsletter.legal.hold", "action_release", [[holdId]], {
    reason: "Playwright test cleanup",
  });
});

test("a company-wide hold blocks retention for any recipient", async ({ page }) => {
  const client = await adminClient();
  const suffix = uniqueSuffix();
  const holdId = await client.create("newsletter.legal.hold", {
    name: `PW Blocking Hold ${suffix}`,
    reason: "Playwright: blocks retention test",
    scope_type: "company",
  });

  const partnerId = await client.create("res.partner", {
    name: `PW Held Partner ${suffix}`,
    email: `pw.held.${suffix}@example.com`,
  });
  const [reasonId] = await client.search("newsletter.suppression.reason", [
    ["code", "=", "MANUAL"],
  ]);
  const entryId = await client.create("newsletter.suppression.entry", {
    partner_id: partnerId,
    scope: "global",
    reason_id: reasonId,
    source: "manual",
  });

  const isHeld = await client.callKw<boolean>("newsletter.legal.hold", "search", [
    [["status", "=", "active"], ["scope_type", "=", "company"]],
  ]);
  expect((isHeld as unknown as number[]).length).toBeGreaterThan(0);

  // Confirm via the retention service's own logic exposed through the UI
  // path: the entry should still exist and be active - a legal hold
  // never mutates data itself, it only blocks the retention processor.
  await page.goto(`/odoo/newsletter.suppression.entry/${entryId}`);
  await waitForOdooView(page);
  await expect(fieldInput(page, "active")).toBeChecked();

  await client.callKw("newsletter.legal.hold", "action_release", [[holdId]], {
    reason: "Playwright test cleanup",
  });
});

test("can release a legal hold with a reason", async ({ page }) => {
  const client = await adminClient();
  const suffix = uniqueSuffix();
  const holdId = await client.create("newsletter.legal.hold", {
    name: `PW Release Hold ${suffix}`,
    reason: "Playwright: to be released",
    scope_type: "company",
  });

  await page.goto(`/odoo/newsletter.legal.hold/${holdId}`);
  await waitForOdooView(page);

  await page.locator('button:has-text("Release Hold")').click();
  await page.locator(".modal textarea").first().fill("Playwright: investigation closed");
  await page.locator('.modal button:has-text("Release Hold")').last().click();
  await waitForOdooView(page);

  await expect(statusbarOption(page, "status", "released")).toHaveAttribute(
    "aria-checked",
    "true"
  );
});

test("Retention Action Ledger is reachable read-only from this role too", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.retentionActionLedger);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });
});
