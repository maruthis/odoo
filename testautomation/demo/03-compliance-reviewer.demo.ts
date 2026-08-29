/** Demo recording - Compliance Reviewer (Demo Playbook §3.3). */
import { test } from "@playwright/test";
import { adminClient, seedDraftCampaign } from "../src/seedData";
import { beat, gotoComplianceMenu, headerButton, statusbarOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Compliance Reviewer walkthrough", async ({ page }) => {
  const client = await adminClient();
  const fixture = await seedDraftCampaign(client, "demo-reviewer");
  await client.callKw("mailing.mailing", "action_submit_content_review", [[fixture.mailingId]]);
  await client.callKw("mailing.mailing", "action_approve_content", [[fixture.mailingId]]);

  // Compliance Review Queue.
  await gotoComplianceMenu(page, MENU.complianceReviewQueue);
  await beat(page, 1800);

  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);
  await beat(page, 1200);

  // Approve compliance.
  await headerButton(page, "action_approve_compliance").click();
  await waitForOdooView(page);
  await beat(page, 2000);

  // Run preflight - this hands off to the newly created Campaign Run.
  await headerButton(page, "action_run_compliance_preflight").click();
  await waitForOdooView(page);
  await statusbarOption(page, "state", "passed").waitFor({ state: "visible" });
  await beat(page, 2500);

  // Show the reconciled eligible/excluded counts.
  await page.locator('.o_notebook a:has-text("Preflight Counts")').click().catch(() => {});
  await beat(page, 2000);

  // Approval History - the append-only record of both decisions above.
  await gotoComplianceMenu(page, MENU.approvalHistory);
  await beat(page, 1800);
});
