/**
 * Captures the screenshots used in the Newsletter Compliance User Guide.
 * Not a test in the pass/fail sense - one continuous walkthrough (same
 * pattern as demo/00-full-platform-e2e.demo.ts: real logins on one page,
 * not swapped storageState contexts) that saves a named PNG at each
 * screen the guide references. Run with:
 *   npx playwright test --config=playwright.screenshots.config.ts
 */
import { test } from "@playwright/test";
import path from "path";
import {
  adminClient,
  advanceToReadyToSend,
  driveRunToArchive,
  seedDraftCampaign,
  uniqueSuffix,
} from "../src/seedData";
import {
  fieldInput,
  gotoComplianceMenu,
  headerButton,
  loginAs,
  selectDropdownOption,
  statusbarOption,
  switchUser,
  waitForOdooView,
} from "../src/nav";
import { MENU } from "../src/menuIds";
import { DEMO_PASSWORD } from "../src/env";

const OUT_DIR = path.join(__dirname, "output");

test("capture guide screenshots", async ({ page }) => {
  test.setTimeout(300_000);
  const client = await adminClient();
  const shot = (name: string) => page.screenshot({ path: path.join(OUT_DIR, `${name}.png`) });

  // ================================================================
  // Public: subscribe (double opt-in) + unsubscribe
  // ================================================================
  // public_subscribe defaults to True on every consent purpose, so this
  // dev DB has accumulated one entry per purpose ever created by any
  // Playwright run this session (dozens) - archive all of them so the
  // subscribe page screenshot shows a clean, realistic list instead of a
  // long scroll of disposable test fixtures. Only ever archives
  // (active=False, reversible, never deletes) - this is a disposable dev
  // sandbox database (see README's "point ODOO_BASE_URL/ODOO_DB at a
  // disposable database" note), not a database anyone depends on.
  const stalePurposeIds = await client.search("newsletter.consent.purpose", [
    ["public_subscribe", "=", true],
  ]);
  if (stalePurposeIds.length) {
    await client.write("newsletter.consent.purpose", stalePurposeIds, { active: false });
  }

  const pubSuffix = uniqueSuffix();
  const purposeId = await client.create("newsletter.consent.purpose", {
    name: "Product Announcements",
    code: `GUIDE_PUB_${pubSuffix}`,
    privacy_notice_version: "v1",
    public_subscribe: true,
  });

  await page.goto("/newsletter-compliance/subscribe");
  await page.fill('input[name="email"]', `guide.subscriber.${pubSuffix}@example.com`);
  await page.fill('input[name="first_name"]', "Jordan");
  await page.fill('input[name="last_name"]', "Rivera");
  await page.locator(`input[name="purpose_ids"][value="${purposeId}"]`).check();
  await page.locator('input[name="consent"]').check();
  await shot("public-01-subscribe-form");
  await page.locator('button:has-text("Subscribe")').click();
  await shot("public-02-subscribe-pending");

  const [consentId] = await client.search("newsletter.consent.record", [
    ["email_normalized", "=", `guide.subscriber.${pubSuffix}@example.com`],
  ]);
  const [consent] = await client.callKw<any[]>("newsletter.consent.record", "read", [
    [consentId],
    ["confirmation_token"],
  ]);
  await page.goto(`/newsletter-compliance/subscribe/confirm/${consent.confirmation_token}`);
  await shot("public-03-subscribe-confirmed");

  // ================================================================
  // Newsletter Author
  // ================================================================
  const main = await seedDraftCampaign(client, "guide-main");

  await loginAs(page, "demo.author", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.myCampaigns);
  await shot("author-01-my-campaigns");

  await page.goto(`/odoo/mailing.mailing/${main.mailingId}`);
  await waitForOdooView(page);
  await shot("author-02-draft-campaign");
  await headerButton(page, "action_submit_content_review").click();
  await waitForOdooView(page);
  await shot("author-03-submitted-for-review");

  // ================================================================
  // Content Approver
  // ================================================================
  await switchUser(page, "demo.approver", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.contentReviewQueue);
  await shot("approver-01-content-review-queue");

  await page.goto(`/odoo/mailing.mailing/${main.mailingId}`);
  await waitForOdooView(page);
  await shot("approver-02-mailing-pending-review");
  await headerButton(page, "action_approve_content").click();
  await waitForOdooView(page);
  await shot("approver-03-content-approved");

  // ================================================================
  // Compliance Reviewer
  // ================================================================
  await switchUser(page, "demo.reviewer", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.complianceReviewQueue);
  await shot("reviewer-01-compliance-review-queue");

  await page.goto(`/odoo/mailing.mailing/${main.mailingId}`);
  await waitForOdooView(page);
  await shot("reviewer-02-mailing-pending-compliance");
  await headerButton(page, "action_approve_compliance").click();
  await waitForOdooView(page);
  await shot("reviewer-03-compliance-approved");
  await headerButton(page, "action_run_compliance_preflight").click();
  await waitForOdooView(page);
  await statusbarOption(page, "state", "passed").waitFor({ state: "visible" });
  await shot("reviewer-04-preflight-passed");
  await page.locator('.o_notebook a:has-text("Preflight Counts")').click().catch(() => {});
  await shot("reviewer-05-preflight-counts");

  const [mailingAfterPreflight] = await client.callKw<any[]>("mailing.mailing", "read", [
    [main.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailingAfterPreflight.current_campaign_run_id[0];

  // ================================================================
  // Compliance Administrator
  // ================================================================
  await switchUser(page, "demo.compliance.admin", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.configConsentPurposes);
  await shot("compliance-admin-01-consent-purposes");

  const suppressPartnerId = await client.create("res.partner", {
    name: "Alex Morgan",
    email: `alex.morgan.${pubSuffix}@example.com`,
  });
  const [manualReasonId] = await client.search("newsletter.suppression.reason", [
    ["code", "=", "MANUAL"],
  ]);
  await client.create("newsletter.suppression.entry", {
    partner_id: suppressPartnerId,
    scope: "global",
    reason_id: manualReasonId,
    source: "manual",
  });
  await gotoComplianceMenu(page, MENU.allSuppressions);
  await shot("compliance-admin-02-suppression-list");

  await gotoComplianceMenu(page, MENU.configDelivery);
  await shot("compliance-admin-03-delivery-settings");

  // ================================================================
  // Campaign Operator
  // ================================================================
  await switchUser(page, "demo.operator", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.readyToSend);
  await shot("operator-01-ready-to-send");

  await page.goto(`/odoo/newsletter.campaign.run/${runId}`);
  await waitForOdooView(page);
  await shot("operator-02-campaign-run-ready");
  await headerButton(page, "action_start_execution").click();
  await waitForOdooView(page);
  await statusbarOption(page, "state", "queued").waitFor({ state: "visible" });
  await shot("operator-03-campaign-run-queued");

  const archivedRun = await driveRunToArchive(
    client,
    "newsletter_compliance.ir_cron_newsletter_dispatch_worker",
    runId
  );

  // ================================================================
  // Privacy Officer
  // ================================================================
  const privacySuffix = uniqueSuffix();
  const privacyPartnerId = await client.create("res.partner", {
    name: "Priya Nair",
    email: `priya.nair.${privacySuffix}@example.com`,
  });
  const privacyRequestId = await client.create("newsletter.privacy.request", {
    request_type: "access",
    requester: "Priya Nair",
    partner_id: privacyPartnerId,
  });

  await switchUser(page, "demo.privacy", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.privacyRequests);
  await shot("privacy-01-requests-list");

  await page.goto(`/odoo/newsletter.privacy.request/${privacyRequestId}`);
  await waitForOdooView(page);
  await shot("privacy-02-new-request");
  await fieldInput(page, "verification_method").fill("Email confirmation");
  await headerButton(page, "action_verify_identity_button").click();
  await waitForOdooView(page);
  await shot("privacy-03-identity-verified");
  await headerButton(page, "action_run_discovery").click();
  await waitForOdooView(page);
  await shot("privacy-04-discovery-complete");

  await gotoComplianceMenu(page, MENU.retentionPolicies);
  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);
  await fieldInput(page, "name").fill("Suppression History - 1 Year");
  await fieldInput(page, "code").fill(`GUIDE_RETENTION_${privacySuffix}`);
  await selectDropdownOption(page, "data_category", "Suppression History");
  await fieldInput(page, "retention_period_days").fill("365");
  await shot("privacy-05-retention-policy-form");
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);

  // ================================================================
  // Legal Hold Administrator
  // ================================================================
  const holdPartnerId = await client.create("res.partner", {
    name: "Sam Chen",
    email: `sam.chen.${privacySuffix}@example.com`,
  });

  await switchUser(page, "demo.legal.hold", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.legalHolds);
  await shot("legalhold-01-holds-list");

  await page.goto("/odoo/newsletter.legal.hold/new");
  await waitForOdooView(page);
  await fieldInput(page, "name").fill("Regulatory Inquiry - Q1");
  await fieldInput(page, "reason").fill("Litigation preservation pending regulator inquiry.");
  await selectDropdownOption(page, "scope_type", "Recipient");
  await page.locator('[name="scope_partner_ids"] input').first().fill("Sam Chen");
  await page.waitForTimeout(700);
  await page.locator(".o-autocomplete--dropdown-menu li, .ui-menu-item").first().click();
  await page.waitForTimeout(500); // tag chip render after selection
  await shot("legalhold-02-new-hold-form");
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);
  await shot("legalhold-03-hold-active");

  await page.locator('button:has-text("Release Hold")').click();
  await page.locator(".modal textarea").first().fill("Inquiry closed - no further action required.");
  await page.locator('.modal button:has-text("Release Hold")').last().click();
  await waitForOdooView(page);
  await shot("legalhold-04-hold-released");

  // ================================================================
  // Compliance Audit Reviewer
  // ================================================================
  await switchUser(page, "demo.auditor", DEMO_PASSWORD);
  await page.goto(`/odoo/newsletter.campaign.archive/${archivedRun.archive_id[0]}`);
  await waitForOdooView(page);
  await shot("auditor-01-locked-archive");

  await gotoComplianceMenu(page, MENU.retentionActionLedger);
  await shot("auditor-02-retention-ledger");

  await gotoComplianceMenu(page, MENU.approvalHistory);
  await shot("auditor-03-approval-history");
});
