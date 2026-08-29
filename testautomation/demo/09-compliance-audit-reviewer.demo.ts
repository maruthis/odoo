/** Demo recording - Compliance Audit Reviewer (Demo Playbook §3.9). */
import { test } from "@playwright/test";
import { adminClient, advanceToReadyToSend, driveRunToArchive, seedDraftCampaign } from "../src/seedData";
import { beat, gotoComplianceMenu, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Compliance Audit Reviewer walkthrough", async ({ page }) => {
  const client = await adminClient();

  // Browse Campaign Runs, Send Events, and Campaign Archives.
  await gotoComplianceMenu(page, MENU.auditCampaignRuns);
  await beat(page, 1600);
  await gotoComplianceMenu(page, MENU.auditSendEvents);
  await beat(page, 1600);
  await gotoComplianceMenu(page, MENU.auditCampaignArchives);
  await beat(page, 1600);

  // Drive a run all the way to a locked archive, then verify its integrity.
  const fixture = await seedDraftCampaign(client, "auditor-archive");
  await advanceToReadyToSend(client, fixture.mailingId);
  const [mailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [fixture.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailing.current_campaign_run_id[0];
  await client.callKw("newsletter.campaign.run", "action_start_execution", [[runId]]);

  const run = await driveRunToArchive(
    client,
    "newsletter_compliance.ir_cron_newsletter_dispatch_worker",
    runId
  );

  await page.goto(`/odoo/newsletter.campaign.archive/${run.archive_id[0]}`);
  await waitForOdooView(page);
  await beat(page, 1800);

  await page.locator('button:has-text("Verify Integrity")').click();
  await beat(page, 2200);

  // Retention Action Ledger and Privacy Requests, both read-only here.
  await gotoComplianceMenu(page, MENU.retentionActionLedger);
  await beat(page, 1600);
  await gotoComplianceMenu(page, MENU.privacyRequests);
  await beat(page, 1600);
});
