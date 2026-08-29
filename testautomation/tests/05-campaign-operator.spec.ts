/** Demo Playbook §3.5 - Campaign Operator. */
import { expect, test } from "@playwright/test";
import {
  adminClient,
  advanceToReadyToSend,
  seedDraftCampaign,
  withCronPaused,
  type CampaignFixture,
} from "../src/seedData";
import { gotoComplianceMenu, headerActionButton, headerButton, statusbarOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

async function seedReadyToSend(label: string): Promise<CampaignFixture> {
  const client = await adminClient();
  const fixture = await seedDraftCampaign(client, label);
  await advanceToReadyToSend(client, fixture.mailingId);
  return fixture;
}

test("Ready to Send lists a campaign that passed preflight", async ({ page }) => {
  await seedReadyToSend("op-ready-list");
  await gotoComplianceMenu(page, MENU.readyToSend);
  await expect(page.locator(".o_list_table")).toBeVisible({ timeout: 15000 });
});

test("Operator can start a send from Ready to Send", async ({ page }) => {
  const fixture = await seedReadyToSend("op-start-send");
  const client = await adminClient();
  const [mailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [fixture.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailing.current_campaign_run_id[0];

  await page.goto(`/odoo/newsletter.campaign.run/${runId}`);
  await waitForOdooView(page);

  await expect(headerButton(page, "action_start_execution")).toBeVisible();
  await headerButton(page, "action_start_execution").click();
  await waitForOdooView(page);

  await expect(statusbarOption(page, "state", "queued")).toHaveAttribute(
    "aria-checked",
    "true"
  );
});

test("Operator can cancel an in-progress execution", async ({ page }) => {
  const fixture = await seedReadyToSend("op-cancel-exec");
  const client = await adminClient();
  const [mailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [fixture.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailing.current_campaign_run_id[0];

  // The live dev server this suite runs against keeps its own 1-minute
  // dispatch cron ticking against the same database - without pausing
  // it, a just-queued single-recipient run can race to "completed"
  // before this test gets to click Cancel. Paused only for the duration
  // of this test, always restored afterward.
  await withCronPaused(
    client,
    "newsletter_compliance.ir_cron_newsletter_dispatch_worker",
    async () => {
      await client.callKw("newsletter.campaign.run", "action_start_execution", [[runId]]);

      await page.goto(`/odoo/newsletter.campaign.run/${runId}`);
      await waitForOdooView(page);

      await headerActionButton(page, "Cancel Execution").click();
      await page.locator(".modal textarea").first().fill("Playwright: pausing this run for review");
      await page.locator('.modal button:has-text("Cancel Execution")').last().click();
      await waitForOdooView(page);
    }
  );

  await expect(statusbarOption(page, "state", "cancelled")).toHaveAttribute(
    "aria-checked",
    "true"
  );
});

test("Active Runs and Completed Runs menus are reachable", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.activeRuns);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });

  await gotoComplianceMenu(page, MENU.completedRuns);
  await expect(page.locator(".o_list_view")).toBeVisible({ timeout: 15000 });
});
