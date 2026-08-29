/** Demo recording - Operations Administrator (Demo Playbook §3.6). */
import { test } from "@playwright/test";
import { adminClient, advanceToReadyToSend, seedDraftCampaign } from "../src/seedData";
import { beat, gotoComplianceMenu, headerButton, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Operations Administrator walkthrough", async ({ page }) => {
  const client = await adminClient();

  // Deliverability settings.
  await gotoComplianceMenu(page, MENU.configDelivery);
  await beat(page, 2200);

  // Inherits the Campaign Operator's Send permission.
  const fixture = await seedDraftCampaign(client, "opsadmin-send");
  await advanceToReadyToSend(client, fixture.mailingId);
  const [mailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [fixture.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailing.current_campaign_run_id[0];

  await page.goto(`/odoo/newsletter.campaign.run/${runId}`);
  await waitForOdooView(page);
  await beat(page, 1500);
  await headerButton(page, "action_start_execution").click();
  await waitForOdooView(page);
  await beat(page, 2200);
});
