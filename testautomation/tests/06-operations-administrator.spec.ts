/** Demo Playbook §3.6 - Operations Administrator (superset of Campaign
 * Operator, plus provider/dispatch configuration). */
import { expect, test } from "@playwright/test";
import { adminClient, advanceToReadyToSend, seedDraftCampaign } from "../src/seedData";
import { gotoComplianceMenu, headerButton, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Operations Administrator can reach Deliverability settings", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.configDelivery);
  await expect(page.locator(".o_form_view")).toBeVisible({ timeout: 15000 });
  await expect(page.locator("text=Delivery Provider")).toBeVisible();
});

test("Operations Administrator inherits Campaign Operator's Send permission", async ({ page }) => {
  const client = await adminClient();
  const fixture = await seedDraftCampaign(client, "opsadmin-send");
  await advanceToReadyToSend(client, fixture.mailingId);
  const [mailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [fixture.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailing.current_campaign_run_id[0];

  await page.goto(`/odoo/newsletter.campaign.run/${runId}`);
  await waitForOdooView(page);

  await expect(headerButton(page, "action_start_execution")).toBeVisible();
});
