/**
 * Demo Playbook §2 - "End-to-End Lifecycle - Who Hands Off to Whom".
 * The flagship test: walks one campaign through every role in sequence,
 * each acting through their own authenticated browser context (their
 * real storageState from global-setup), exactly mirroring the sequence
 * diagram in the Demo Playbook.
 */
import { expect, test, chromium, type Browser } from "@playwright/test";
import path from "path";
import { adminClient, driveRunToArchive, seedDraftCampaign, uniqueSuffix } from "../src/seedData";
import { waitForOdooView, headerButton, selectDropdownOption, statusbarOption, fieldInput } from "../src/nav";
import { OdooClient } from "../src/odooClient";

const AUTH_DIR = path.join(__dirname, "..", ".auth");

async function pageAs(browser: Browser, roleKey: string) {
  const context = await browser.newContext({
    storageState: path.join(AUTH_DIR, `${roleKey}.json`),
  });
  return context.newPage();
}

test("full campaign lifecycle: Author -> Content Approver -> Compliance Reviewer -> Operator -> Archive -> Audit", async () => {
  test.setTimeout(120_000);

  const client = await adminClient();
  const fixture = await seedDraftCampaign(client, "lifecycle");

  const browser = await chromium.launch();

  // 1. Author submits for content review.
  const authorPage = await pageAs(browser, "author");
  await authorPage.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(authorPage);
  await headerButton(authorPage, "action_submit_content_review").click();
  await waitForOdooView(authorPage);
  await expect(
    statusbarOption(authorPage, "compliance_state", "content_review")
  ).toHaveAttribute("aria-checked", "true");
  await authorPage.context().close();

  // 2. Content Approver approves content.
  const approverPage = await pageAs(browser, "contentApprover");
  await approverPage.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(approverPage);
  await headerButton(approverPage, "action_approve_content").click();
  await waitForOdooView(approverPage);
  await expect(
    statusbarOption(approverPage, "compliance_state", "compliance_review")
  ).toHaveAttribute("aria-checked", "true");
  await approverPage.context().close();

  // 3. Compliance Reviewer approves compliance, then runs preflight.
  const reviewerPage = await pageAs(browser, "complianceReviewer");
  await reviewerPage.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(reviewerPage);
  await headerButton(reviewerPage, "action_approve_compliance").click();
  await waitForOdooView(reviewerPage);
  await headerButton(reviewerPage, "action_run_compliance_preflight").click();
  await waitForOdooView(reviewerPage);
  // action_run_compliance_preflight() navigates to the new Campaign
  // Run's own form rather than staying on the mailing - its state
  // reaching "passed" is what drives the mailing's compliance_state to
  // "ready" behind the scenes (see the equivalent note in
  // 03-compliance-reviewer.spec.ts).
  await expect(statusbarOption(reviewerPage, "state", "passed")).toHaveAttribute(
    "aria-checked",
    "true"
  );
  await reviewerPage.context().close();

  const [mailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [fixture.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailing.current_campaign_run_id[0];

  // 4. Campaign Operator starts the send.
  const operatorPage = await pageAs(browser, "operator");
  await operatorPage.goto(`/odoo/newsletter.campaign.run/${runId}`);
  await waitForOdooView(operatorPage);
  await headerButton(operatorPage, "action_start_execution").click();
  await waitForOdooView(operatorPage);
  await expect(statusbarOption(operatorPage, "state", "queued")).toHaveAttribute(
    "aria-checked",
    "true"
  );
  await operatorPage.context().close();

  // Dispatch is normally driven by the 1-minute cron.
  const run = await driveRunToArchive(
    client,
    "newsletter_compliance.ir_cron_newsletter_dispatch_worker",
    runId
  );
  expect(run.archive_id, "expected the run to eventually archive").toBeTruthy();

  // 5. Compliance Audit Reviewer reconstructs the campaign from the
  // archive, read-only, and verifies its integrity - closing the loop
  // the Demo Playbook describes.
  const auditorPage = await pageAs(browser, "auditor");
  await auditorPage.goto(`/odoo/newsletter.campaign.archive/${run.archive_id[0]}`);
  await waitForOdooView(auditorPage);
  await auditorPage.locator('button:has-text("Verify Integrity")').click();
  await expect(auditorPage.locator(".o_notification, .modal")).toBeVisible({ timeout: 10000 });
  await auditorPage.context().close();

  await browser.close();
});

test("erasure vs. legal hold: a hold placed first blocks a later erasure request", async () => {
  test.setTimeout(60_000);

  const client = await adminClient();
  const suffix = uniqueSuffix();
  const partnerId = await client.create("res.partner", {
    name: `PW Lifecycle Held Subject ${suffix}`,
    email: `pw.lifecycle.held.${suffix}@example.com`,
  });
  const [reasonId] = await client.search("newsletter.suppression.reason", [
    ["code", "=", "MANUAL"],
  ]);
  const suppressionId = await client.create("newsletter.suppression.entry", {
    partner_id: partnerId,
    scope: "global",
    reason_id: reasonId,
    source: "manual",
  });

  const browser = await chromium.launch();

  // Legal Hold Administrator places a hold on this specific recipient.
  const legalPage = await pageAs(browser, "legalHoldAdmin");
  await legalPage.goto("/odoo/newsletter.legal.hold/new");
  await waitForOdooView(legalPage);
  await fieldInput(legalPage, "name").fill(`PW Lifecycle Hold ${suffix}`);
  await fieldInput(legalPage, "reason").fill("Playwright: pre-erasure hold");
  await selectDropdownOption(legalPage, "scope_type", "Recipient");
  await legalPage
    .locator('[name="scope_partner_ids"] input')
    .first()
    .fill(`PW Lifecycle Held Subject ${suffix}`);
  await legalPage.waitForTimeout(700);
  await legalPage.locator(".o-autocomplete--dropdown-menu li, .ui-menu-item").first().click();
  await legalPage.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(legalPage);
  await legalPage.context().close();

  // Privacy Officer files and executes an erasure request for the same
  // recipient - it must be blocked, not silently succeed.
  const client2 = await adminClient();
  const requestId = await client2.create("newsletter.privacy.request", {
    request_type: "erasure",
    requester: `PW Lifecycle Held Subject ${suffix}`,
    partner_id: partnerId,
  });

  const privacyPage = await pageAs(browser, "privacyOfficer");
  await privacyPage.goto(`/odoo/newsletter.privacy.request/${requestId}`);
  await waitForOdooView(privacyPage);
  await fieldInput(privacyPage, "verification_method").fill("Email confirmation");
  await headerButton(privacyPage, "action_verify_identity_button").click();
  await waitForOdooView(privacyPage);

  // action_run_discovery() moves status from "discovery" to
  // "legal_review" - only then does the Execute button's visibility
  // condition (status in ('decision', 'legal_review')) allow it to show.
  await headerButton(privacyPage, "action_run_discovery").click();
  await waitForOdooView(privacyPage);

  await expect(
    privacyPage.locator('.o_statusbar_buttons button:has-text("Execute")')
  ).toBeVisible();
  await privacyPage.locator('.o_statusbar_buttons button:has-text("Execute")').click();
  await privacyPage.locator('.modal button:has-text("Execute")').click();
  await waitForOdooView(privacyPage);
  await privacyPage.context().close();

  await browser.close();

  const [suppression] = await client2.callKw<any[]>("newsletter.suppression.entry", "read", [
    [suppressionId],
    ["identity_state", "partner_id"],
  ]);
  expect(suppression.identity_state).toBe("identified");
  expect(suppression.partner_id).toBeTruthy();

  const blockedActions = await client2.search("newsletter.retention.action", [
    ["privacy_request_id", "=", requestId],
    ["result", "=", "blocked"],
  ]);
  expect(blockedActions.length).toBeGreaterThan(0);
});
