/** Demo recording - Campaign Operator (Demo Playbook §3.5). */
import { test } from "@playwright/test";
import { adminClient, advanceToReadyToSend, seedDraftCampaign, withCronPaused } from "../src/seedData";
import { beat, gotoComplianceMenu, headerActionButton, headerButton, statusbarOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Campaign Operator walkthrough", async ({ page }) => {
  const client = await adminClient();

  // Ready to Send queue.
  const listed = await seedDraftCampaign(client, "op-ready-list");
  await advanceToReadyToSend(client, listed.mailingId);
  await gotoComplianceMenu(page, MENU.readyToSend);
  await beat(page, 2000);

  // Start a send.
  const toStart = await seedDraftCampaign(client, "op-start-send");
  await advanceToReadyToSend(client, toStart.mailingId);
  const [startMailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [toStart.mailingId],
    ["current_campaign_run_id"],
  ]);
  const startRunId = startMailing.current_campaign_run_id[0];
  await page.goto(`/odoo/newsletter.campaign.run/${startRunId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await headerButton(page, "action_start_execution").click();
  await waitForOdooView(page);
  await statusbarOption(page, "state", "queued").waitFor({ state: "visible" });
  await beat(page, 2000);

  // Cancel an in-progress execution (cron paused so the demo can catch it
  // mid-flight before the live dispatch cron completes it).
  const toCancel = await seedDraftCampaign(client, "op-cancel-exec");
  await advanceToReadyToSend(client, toCancel.mailingId);
  const [cancelMailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [toCancel.mailingId],
    ["current_campaign_run_id"],
  ]);
  const cancelRunId = cancelMailing.current_campaign_run_id[0];

  await withCronPaused(
    client,
    "newsletter_compliance.ir_cron_newsletter_dispatch_worker",
    async () => {
      await client.callKw("newsletter.campaign.run", "action_start_execution", [[cancelRunId]]);

      await page.goto(`/odoo/newsletter.campaign.run/${cancelRunId}`);
      await waitForOdooView(page);
      await beat(page, 1200);

      await headerActionButton(page, "Cancel Execution").click();
      await beat(page, 600);
      await page.locator(".modal textarea").first().fill("Pausing this run for review.");
      await beat(page, 800);
      await page.locator('.modal button:has-text("Cancel Execution")').last().click();
      await waitForOdooView(page);
      await beat(page, 2000);
    }
  );

  // Active Runs and Completed Runs.
  await gotoComplianceMenu(page, MENU.activeRuns);
  await beat(page, 1800);
  await gotoComplianceMenu(page, MENU.completedRuns);
  await beat(page, 1800);
});
