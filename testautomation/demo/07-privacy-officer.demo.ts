/** Demo recording - Privacy Officer (Demo Playbook §3.7). */
import { test } from "@playwright/test";
import { adminClient, uniqueSuffix } from "../src/seedData";
import { beat, fieldInput, gotoComplianceMenu, headerButton, selectDropdownOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Privacy Officer walkthrough", async ({ page }) => {
  const client = await adminClient();
  const suffix = uniqueSuffix();

  // Log a new privacy request and verify identity.
  const partnerId = await client.create("res.partner", {
    name: `Demo Privacy Subject ${suffix}`,
    email: `demo.privacy.${suffix}@example.com`,
  });
  const requestId = await client.create("newsletter.privacy.request", {
    request_type: "access",
    requester: `Demo Privacy Subject ${suffix}`,
    partner_id: partnerId,
  });

  await page.goto(`/odoo/newsletter.privacy.request/${requestId}`);
  await waitForOdooView(page);
  await beat(page, 1500);

  await fieldInput(page, "verification_method").fill("Email confirmation");
  await beat(page, 600);
  await headerButton(page, "action_verify_identity_button").click();
  await waitForOdooView(page);
  await beat(page, 1800);

  // Run discovery.
  await headerButton(page, "action_run_discovery").click();
  await waitForOdooView(page);
  await beat(page, 2200);

  // Retention Policies - create one and preview its impact.
  await gotoComplianceMenu(page, MENU.retentionPolicies);
  await beat(page, 1500);
  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);

  await fieldInput(page, "name").fill(`Demo Retention Policy ${suffix}`);
  await beat(page, 400);
  await fieldInput(page, "code").fill(`DEMO_RETENTION_${suffix}`);
  await beat(page, 400);
  await selectDropdownOption(page, "data_category", "Suppression History");
  await beat(page, 400);
  await fieldInput(page, "retention_period_days").fill("365");
  await beat(page, 600);
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);
  await beat(page, 1500);

  await page.locator('button:has-text("Preview Impact")').click();
  await beat(page, 600);
  await page.locator('.modal button:has-text("Preview")').click();
  await beat(page, 2200);

  // Privacy Requests list.
  await gotoComplianceMenu(page, MENU.privacyRequests);
  await beat(page, 1800);
});
