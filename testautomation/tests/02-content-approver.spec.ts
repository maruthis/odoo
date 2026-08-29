/** Demo Playbook §3.2 - Content Approver. */
import { expect, test } from "@playwright/test";
import { adminClient, seedDraftCampaign, type CampaignFixture } from "../src/seedData";
import { gotoComplianceMenu, headerButton, statusbarOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

async function seedInContentReview(label: string): Promise<CampaignFixture> {
  const client = await adminClient();
  const fixture = await seedDraftCampaign(client, label);
  await client.callKw("mailing.mailing", "action_submit_content_review", [[fixture.mailingId]]);
  return fixture;
}

test("Content Review Queue lists a campaign awaiting content review", async ({ page }) => {
  await seedInContentReview("cr-queue");
  await gotoComplianceMenu(page, MENU.contentReviewQueue);
  await expect(page.locator(".o_list_table")).toBeVisible({ timeout: 15000 });
});

test("Content Approver can approve content", async ({ page }) => {
  const fixture = await seedInContentReview("cr-approve");
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);

  await expect(headerButton(page, "action_approve_content")).toBeVisible();
  await headerButton(page, "action_approve_content").click();
  await waitForOdooView(page);

  await expect(statusbarOption(page, "compliance_state", "compliance_review")).toHaveAttribute(
    "aria-checked",
    "true"
  );
});

test("Content Approver can reject content with a reason", async ({ page }) => {
  const fixture = await seedInContentReview("cr-reject");
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);

  await page.locator('.o_statusbar_buttons button:has-text("Reject")').click();
  await page.locator(".modal textarea").first().fill("Playwright: subject line needs rework");
  await page
    .locator('.modal button:has-text("Reject")')
    .last()
    .click();
  await waitForOdooView(page);

  // Rejecting doesn't leave the campaign in a dead-end "rejected" state -
  // action_reject() sends it back to the wizard's return_to state
  // (Draft by default) so the Author can fix it and resubmit. The
  // rejection itself is recorded as a "rejected" decision in campaign
  // approval history, not as compliance_state itself.
  await expect(statusbarOption(page, "compliance_state", "draft")).toHaveAttribute(
    "aria-checked",
    "true"
  );

  const client = await adminClient();
  const approvalIds = await client.search("newsletter.campaign.approval", [
    ["mailing_id", "=", fixture.mailingId],
    ["decision", "=", "rejected"],
  ]);
  expect(approvalIds.length).toBeGreaterThan(0);
});

test("Content Approver cannot see the Approve Compliance button", async ({ page }) => {
  const fixture = await seedInContentReview("cr-no-compliance-approve");
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);

  await expect(headerButton(page, "action_approve_compliance")).toHaveCount(0);
});
