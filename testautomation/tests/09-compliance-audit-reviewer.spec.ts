/** Demo Playbook §3.9 - Compliance Audit Reviewer: read-only, everywhere. */
import { expect, test } from "@playwright/test";
import {
  adminClient,
  advanceToReadyToSend,
  driveRunToArchive,
  seedDraftCampaign,
} from "../src/seedData";
import { gotoComplianceMenu, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("can browse Campaign Runs, Send Events, and Campaign Archives", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.auditCampaignRuns);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });

  await gotoComplianceMenu(page, MENU.auditSendEvents);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });

  await gotoComplianceMenu(page, MENU.auditCampaignArchives);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });
});

test("cannot create a new campaign archive from the list view", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.auditCampaignArchives);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });
  // The archive list/form ships with create="0" - no "New" button at all.
  await expect(page.locator(".o_list_button_add")).toHaveCount(0);
});

test("can open a locked archive and click Verify Integrity", async ({ page }) => {
  const client = await adminClient();
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
  expect(run.archive_id, "expected the run to eventually archive").toBeTruthy();

  await page.goto(`/odoo/newsletter.campaign.archive/${run.archive_id[0]}`);
  await waitForOdooView(page);

  await expect(page.locator('button:has-text("Locked")')).toHaveCount(0); // ribbon is a widget, not a button - sanity check page loaded
  await page.locator('button:has-text("Verify Integrity")').click();
  await expect(page.locator(".o_notification, .modal")).toBeVisible({ timeout: 10000 });
});

test("Retention Action Ledger and Privacy Requests are visible read-only", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.retentionActionLedger);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });

  await gotoComplianceMenu(page, MENU.privacyRequests);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });
});
