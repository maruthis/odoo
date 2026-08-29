/** Demo recording - Content Approver (Demo Playbook §3.2). */
import { test } from "@playwright/test";
import { adminClient, seedDraftCampaign } from "../src/seedData";
import { beat, gotoComplianceMenu, headerButton, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

async function seedInContentReview(client: any, label: string) {
  const fixture = await seedDraftCampaign(client, label);
  await client.callKw("mailing.mailing", "action_submit_content_review", [[fixture.mailingId]]);
  return fixture;
}

test("Content Approver walkthrough", async ({ page }) => {
  const client = await adminClient();
  const toApprove = await seedInContentReview(client, "demo-approve");
  const toReject = await seedInContentReview(client, "demo-reject");

  // Content Review Queue.
  await gotoComplianceMenu(page, MENU.contentReviewQueue);
  await beat(page, 1800);

  // Approve one.
  await page.goto(`/odoo/mailing.mailing/${toApprove.mailingId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await headerButton(page, "action_approve_content").click();
  await waitForOdooView(page);
  await beat(page, 2000);

  // Reject another, with a reason.
  await page.goto(`/odoo/mailing.mailing/${toReject.mailingId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await page.locator('.o_statusbar_buttons button:has-text("Reject")').click();
  await beat(page, 600);
  await page.locator(".modal textarea").first().fill("Subject line needs to be reworked before this can proceed.");
  await beat(page, 800);
  await page.locator('.modal button:has-text("Reject")').last().click();
  await waitForOdooView(page);
  await beat(page, 2000);
});
