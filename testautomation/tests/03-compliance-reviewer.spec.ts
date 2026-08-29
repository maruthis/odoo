/** Demo Playbook §3.3 - Compliance Reviewer. */
import { expect, test } from "@playwright/test";
import { adminClient, seedDraftCampaign, type CampaignFixture } from "../src/seedData";
import { gotoComplianceMenu, headerButton, statusbarOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

async function seedInComplianceReview(label: string): Promise<CampaignFixture> {
  const client = await adminClient();
  const fixture = await seedDraftCampaign(client, label);
  await client.callKw("mailing.mailing", "action_submit_content_review", [[fixture.mailingId]]);
  await client.callKw("mailing.mailing", "action_approve_content", [[fixture.mailingId]]);
  return fixture;
}

test("Compliance Review Queue lists a campaign awaiting compliance review", async ({ page }) => {
  await seedInComplianceReview("comp-queue");
  await gotoComplianceMenu(page, MENU.complianceReviewQueue);
  await expect(page.locator(".o_list_table")).toBeVisible({ timeout: 15000 });
});

test("Compliance Reviewer can approve compliance, moving to Preflight Required", async ({
  page,
}) => {
  const fixture = await seedInComplianceReview("comp-approve");
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);

  await expect(headerButton(page, "action_approve_compliance")).toBeVisible();
  await headerButton(page, "action_approve_compliance").click();
  await waitForOdooView(page);

  await expect(
    statusbarOption(page, "compliance_state", "preflight_required")
  ).toHaveAttribute("aria-checked", "true");
});

test("Compliance Reviewer can run preflight and reach Ready to Send", async ({ page }) => {
  const fixture = await seedInComplianceReview("comp-preflight");
  const client = await adminClient();
  await client.callKw("mailing.mailing", "action_approve_compliance", [[fixture.mailingId]]);

  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);

  await expect(headerButton(page, "action_run_compliance_preflight")).toBeVisible();
  await headerButton(page, "action_run_compliance_preflight").click();
  await waitForOdooView(page);

  // action_run_compliance_preflight() navigates straight to the newly
  // created Campaign Run's own form (Demo Playbook §3.3 - "Inspect a
  // preflight result") rather than staying on the mailing - its state
  // reaching "passed" is what actually drives the mailing's
  // compliance_state to "ready" behind the scenes.
  await expect(statusbarOption(page, "state", "passed")).toHaveAttribute("aria-checked", "true");
  await expect(page.locator("text=Eligible").first()).toBeVisible();

  const client2 = await adminClient();
  const [mailing] = await client2.callKw<any[]>("mailing.mailing", "read", [
    [fixture.mailingId],
    ["compliance_state"],
  ]);
  expect(mailing.compliance_state).toBe("ready");
});

test("Approval History records the content and compliance approvals", async ({ page }) => {
  const fixture = await seedInComplianceReview("comp-history");
  const client = await adminClient();
  await client.callKw("mailing.mailing", "action_approve_compliance", [[fixture.mailingId]]);

  await gotoComplianceMenu(page, MENU.approvalHistory);
  await expect(page.locator(".o_list_table")).toBeVisible({ timeout: 15000 });
});
