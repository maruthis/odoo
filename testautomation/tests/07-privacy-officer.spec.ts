/** Demo Playbook §3.7 - Privacy Officer. */
import { expect, test } from "@playwright/test";
import { adminClient, uniqueSuffix } from "../src/seedData";
import { fieldInput, gotoComplianceMenu, headerButton, selectDropdownOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("can log a new privacy request and verify identity", async ({ page }) => {
  const client = await adminClient();
  const suffix = uniqueSuffix();
  const partnerId = await client.create("res.partner", {
    name: `PW Privacy Subject ${suffix}`,
    email: `pw.privacy.${suffix}@example.com`,
  });
  const requestId = await client.create("newsletter.privacy.request", {
    request_type: "access",
    requester: `PW Privacy Subject ${suffix}`,
    partner_id: partnerId,
  });

  await page.goto(`/odoo/newsletter.privacy.request/${requestId}`);
  await waitForOdooView(page);

  // The button wraps action_verify_identity(self.verification_method) -
  // it requires a method to already be filled in, otherwise it raises
  // "A verification method is required."
  await fieldInput(page, "verification_method").fill("Email confirmation");
  await expect(headerButton(page, "action_verify_identity_button")).toBeVisible();
  await headerButton(page, "action_verify_identity_button").click();
  await waitForOdooView(page);

  const [request] = await client.callKw<any[]>("newsletter.privacy.request", "read", [
    [requestId],
    ["identity_verified", "status"],
  ]);
  expect(request.identity_verified).toBe(true);
});

test("can run discovery on a privacy request", async ({ page }) => {
  const client = await adminClient();
  const suffix = uniqueSuffix();
  const partnerId = await client.create("res.partner", {
    name: `PW Discovery Subject ${suffix}`,
    email: `pw.discovery.${suffix}@example.com`,
  });
  const requestId = await client.create("newsletter.privacy.request", {
    request_type: "access",
    requester: `PW Discovery Subject ${suffix}`,
    partner_id: partnerId,
  });
  await client.callKw("newsletter.privacy.request", "action_verify_identity", [
    [requestId],
    "email_confirmation",
  ]);

  await page.goto(`/odoo/newsletter.privacy.request/${requestId}`);
  await waitForOdooView(page);

  await headerButton(page, "action_run_discovery").click();
  await waitForOdooView(page);

  const [request] = await client.callKw<any[]>("newsletter.privacy.request", "read", [
    [requestId],
    ["discovery_counts"],
  ]);
  expect(request.discovery_counts).toBeTruthy();
});

test("can create a retention policy and preview its impact", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.retentionPolicies);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });

  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);

  const suffix = uniqueSuffix();
  await fieldInput(page, "name").fill(`PW Retention Policy ${suffix}`);
  await fieldInput(page, "code").fill(`PW_RETENTION_${suffix}`);
  await selectDropdownOption(page, "data_category", "Suppression History");
  await fieldInput(page, "retention_period_days").fill("365");
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);

  await page.locator('button:has-text("Preview Impact")').click();
  await page.locator('.modal button:has-text("Preview")').click();
  // preview_result is a readonly Text field - Odoo renders it as plain
  // text content, not a textarea/pre element.
  await expect(page.locator("text=Dry-run preview for policy")).toBeVisible({ timeout: 10000 });
});

test("Privacy Requests menu is reachable", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.privacyRequests);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });
});
