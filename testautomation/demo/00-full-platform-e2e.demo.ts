/**
 * Full platform E2E walkthrough - one continuous recording covering every
 * requirement phase, R1 through R6, from mydocs/Custom Module R1.md -
 * R6.md (all built on top of Odoo's native Email Marketing app):
 *
 *   R1 - Foundation: consent purposes, consent register, suppression
 *        register, reinstatement.
 *   R2 - Campaign Governance: compliance metadata on mailing.mailing,
 *        content review.
 *   R3 - Preflight & Recipient Eligibility: compliance approval, frozen
 *        eligible population.
 *   R4 - Execution, Send Event Ledger & Immutable Archive.
 *   R5 - Delivery Feedback: authenticated provider webhook -> automatic
 *        suppression, self-service unsubscribe, operational alerting.
 *   R6 - Privacy Lifecycle: privacy request execution, retention policy,
 *        legal hold blocking erasure, audit evidence export.
 *
 * Unlike the per-role demo/*.demo.ts files (each its own storageState,
 * its own video), this test stays on ONE page/context for the whole
 * recording and switches users via the real login form (nav.ts's
 * loginAs/switchUser) - swapping storageState contexts would start a
 * separate video per context, defeating the point of a single
 * comprehensive recording.
 */
import { test } from "@playwright/test";
import {
  adminClient,
  advanceToReadyToSend,
  driveRunToArchive,
  ensureGenericProviderSecret,
  pollUntil,
  postProviderWebhookEvent,
  seedDraftCampaign,
  triggerCron,
  uniqueSuffix,
} from "../src/seedData";
import {
  beat,
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

test("Full platform E2E walkthrough - R1 through R6", async ({ page }) => {
  test.setTimeout(600_000);
  const client = await adminClient();
  await ensureGenericProviderSecret(client);

  // ================================================================
  // R1 - Foundation: consent primitives + suppression register
  // ================================================================
  await loginAs(page, "demo.compliance.admin", DEMO_PASSWORD);
  const r1 = uniqueSuffix();

  // Consent Purpose Master.
  await gotoComplianceMenu(page, MENU.configConsentPurposes);
  await beat(page, 1200);
  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);
  await fieldInput(page, "name").fill("R1 Newsletter Announcements");
  await beat(page, 300);
  await fieldInput(page, "code").fill(`R1_ANNOUNCEMENTS_${r1}`);
  await beat(page, 300);
  await fieldInput(page, "privacy_notice_version").fill("v1.0");
  await beat(page, 500);
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);
  await beat(page, 1500);

  // Consent Register.
  await gotoComplianceMenu(page, MENU.activeConsents);
  await beat(page, 1500);

  // Suppression Register - manual suppression + reinstatement.
  const r1PartnerId = await client.create("res.partner", {
    name: `R1 Reinstate Contact ${r1}`,
    email: `r1.reinstate.${r1}@example.com`,
  });
  const [manualReasonId] = await client.search("newsletter.suppression.reason", [
    ["code", "=", "MANUAL"],
  ]);
  const r1SuppressionId = await client.create("newsletter.suppression.entry", {
    partner_id: r1PartnerId,
    scope: "global",
    reason_id: manualReasonId,
    source: "manual",
  });
  await page.goto(`/odoo/newsletter.suppression.entry/${r1SuppressionId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await page.locator('button:has-text("Reinstate")').click();
  await beat(page, 500);
  await page.locator(".modal textarea").first().fill("Confirmed opt-back-in for the platform walkthrough.");
  await beat(page, 700);
  await page.locator('.modal button:has-text("Reinstate")').last().click();
  await waitForOdooView(page);
  await beat(page, 1500);

  await gotoComplianceMenu(page, MENU.allSuppressions);
  await beat(page, 1500);

  // ================================================================
  // R2 - Campaign Governance: mailing.mailing extension + content review
  // ================================================================
  const main = await seedDraftCampaign(client, "platform-main");

  await switchUser(page, "demo.author", DEMO_PASSWORD);
  await page.goto(`/odoo/mailing.mailing/${main.mailingId}`);
  await waitForOdooView(page);
  await beat(page, 2000); // compliance metadata: owner, brand, consent purpose, ID
  await headerButton(page, "action_submit_content_review").click();
  await waitForOdooView(page);
  await beat(page, 1800);

  await switchUser(page, "demo.approver", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.contentReviewQueue);
  await beat(page, 1500);
  await page.goto(`/odoo/mailing.mailing/${main.mailingId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await headerButton(page, "action_approve_content").click();
  await waitForOdooView(page);
  await beat(page, 1800);

  // ================================================================
  // R3 - Preflight & Recipient Eligibility
  // ================================================================
  await switchUser(page, "demo.reviewer", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.complianceReviewQueue);
  await beat(page, 1500);
  await page.goto(`/odoo/mailing.mailing/${main.mailingId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await headerButton(page, "action_approve_compliance").click();
  await waitForOdooView(page);
  await beat(page, 1500);
  await headerButton(page, "action_run_compliance_preflight").click();
  await waitForOdooView(page);
  await statusbarOption(page, "state", "passed").waitFor({ state: "visible" });
  await beat(page, 2200);
  await page.locator('.o_notebook a:has-text("Preflight Counts")').click().catch(() => {});
  await beat(page, 1800);

  const [mailingAfterPreflight] = await client.callKw<any[]>("mailing.mailing", "read", [
    [main.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailingAfterPreflight.current_campaign_run_id[0];

  // ================================================================
  // R4 - Execution, Send Event Ledger & Immutable Archive
  // ================================================================
  await switchUser(page, "demo.operator", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.readyToSend);
  await beat(page, 1500);
  await page.goto(`/odoo/newsletter.campaign.run/${runId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await headerButton(page, "action_start_execution").click();
  await waitForOdooView(page);
  await statusbarOption(page, "state", "queued").waitFor({ state: "visible" });
  await beat(page, 2000);

  await gotoComplianceMenu(page, MENU.activeRuns);
  await beat(page, 1500);

  const archivedRun = await driveRunToArchive(
    client,
    "newsletter_compliance.ir_cron_newsletter_dispatch_worker",
    runId
  );

  await switchUser(page, "demo.auditor", DEMO_PASSWORD);
  await page.goto(`/odoo/newsletter.campaign.archive/${archivedRun.archive_id[0]}`);
  await waitForOdooView(page);
  await beat(page, 1800);
  await page.locator('button:has-text("Verify Integrity")').click();
  await beat(page, 2200);

  // ================================================================
  // R5 - Delivery Feedback, Bounce/Complaint/Unsubscribe & Monitoring
  // ================================================================

  // Authenticated provider webhook -> automatic suppression.
  const r5 = await seedDraftCampaign(client, "platform-bounce");
  await advanceToReadyToSend(client, r5.mailingId);
  const [r5Mailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [r5.mailingId],
    ["current_campaign_run_id"],
  ]);
  const r5RunId = r5Mailing.current_campaign_run_id[0];
  await client.callKw("newsletter.campaign.run", "action_start_execution", [[r5RunId]]);
  await triggerCron(client, "newsletter_compliance.ir_cron_newsletter_dispatch_worker");

  // This dev environment has no outgoing SMTP relay, so a dispatch never
  // reaches a real provider and never gets a real message id to
  // correlate a webhook event against - write one directly (the same
  // "simulate the piece the sandbox can't do" shortcut driveRunToArchive
  // already uses for retries) so the rest of the pipeline - webhook
  // authentication, correlation, classification, automatic suppression -
  // runs for real, against the real controller.
  const [r5Eligibility] = await client.search("newsletter.recipient.eligibility", [
    ["campaign_run_id", "=", r5RunId],
  ]);
  const syntheticMessageId = `demo-msg-${uniqueSuffix()}`;
  await client.write("newsletter.recipient.eligibility", [r5Eligibility], {
    provider_message_id: syntheticMessageId,
  });

  await postProviderWebhookEvent({
    provider_event_id: `evt-demo-${uniqueSuffix()}`,
    provider_message_id: syntheticMessageId,
    event_type: "hard_bounce",
    event_timestamp: new Date().toISOString(),
    email: r5.partnerEmail,
    bounce_type: "permanent",
  });
  await triggerCron(client, "newsletter_compliance.ir_cron_newsletter_process_provider_events");

  await switchUser(page, "demo.compliance.admin", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.deliveryEvents);
  await beat(page, 2000);
  await gotoComplianceMenu(page, MENU.allSuppressions);
  await beat(page, 1800);

  // Self-service one-click unsubscribe - the recipient-facing side of the
  // same suppression register, reached with no login at all.
  const r5b = await seedDraftCampaign(client, "platform-unsubscribe");
  await advanceToReadyToSend(client, r5b.mailingId);
  const [r5bMailing] = await client.callKw<any[]>("mailing.mailing", "read", [
    [r5b.mailingId],
    ["current_campaign_run_id"],
  ]);
  await client.callKw("newsletter.campaign.run", "action_start_execution", [
    [r5bMailing.current_campaign_run_id[0]],
  ]);
  await triggerCron(client, "newsletter_compliance.ir_cron_newsletter_dispatch_worker");
  const [mailRecordId] = await pollUntil(
    () => client.search("mail.mail", [["email_to", "=", r5b.partnerEmail]], { order: "id desc", limit: 1 }),
    (ids) => ids.length > 0
  );
  const [mailRecord] = await client.callKw<any[]>("mail.mail", "read", [[mailRecordId], ["body_html"]]);
  const unsubscribeMatch = /href="([^"]*\/newsletter-compliance\/unsubscribe\/[^"]+)"/.exec(
    mailRecord.body_html
  );
  await page.goto(unsubscribeMatch![1]);
  await beat(page, 1500);
  await page.locator('input[name="choice"][value="all"]').check();
  await beat(page, 500);
  await page.locator('button:has-text("Confirm")').click();
  await beat(page, 1800);

  // Operational monitoring - a bounce-threshold alert (seeded at the
  // metric values a real repeated-bounce run would eventually reach),
  // acknowledged then resolved by an operator through the real workflow.
  const r5AlertId = await client.create("newsletter.compliance.alert", {
    alert_type: "bounce_threshold",
    severity: "critical",
    campaign_run_id: r5RunId,
    metric_name: "bounce_rate",
    metric_value: 0.42,
    threshold_value: 0.05,
  });
  await switchUser(page, "demo.compliance.admin", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.activeAlerts);
  await beat(page, 1500);
  await page.goto(`/odoo/newsletter.compliance.alert/${r5AlertId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await page.locator('.o_statusbar_buttons button:has-text("Acknowledge")').click();
  await waitForOdooView(page);
  await beat(page, 1200);
  await page.locator('.o_statusbar_buttons button:has-text("Resolve")').click();
  await waitForOdooView(page);
  await beat(page, 2000);

  // ================================================================
  // R6 - Privacy Lifecycle, Retention, Legal Hold & Evidence Export
  // ================================================================
  const r6 = uniqueSuffix();

  // Happy-path privacy request: verify identity, run discovery, execute.
  const r6PartnerId = await client.create("res.partner", {
    name: `R6 Access Subject ${r6}`,
    email: `r6.access.${r6}@example.com`,
  });
  const r6RequestId = await client.create("newsletter.privacy.request", {
    request_type: "access",
    requester: `R6 Access Subject ${r6}`,
    partner_id: r6PartnerId,
  });

  await switchUser(page, "demo.privacy", DEMO_PASSWORD);
  await page.goto(`/odoo/newsletter.privacy.request/${r6RequestId}`);
  await waitForOdooView(page);
  await beat(page, 1500);
  await fieldInput(page, "verification_method").fill("Email confirmation");
  await beat(page, 500);
  await headerButton(page, "action_verify_identity_button").click();
  await waitForOdooView(page);
  await beat(page, 1500);
  await headerButton(page, "action_run_discovery").click();
  await waitForOdooView(page);
  await beat(page, 2000);
  await page.locator('.o_statusbar_buttons button:has-text("Execute")').click();
  await beat(page, 600);
  await page.locator('.modal button:has-text("Execute")').click();
  await waitForOdooView(page);
  await beat(page, 2000);

  // Retention policy configuration + impact preview.
  await gotoComplianceMenu(page, MENU.retentionPolicies);
  await beat(page, 1500);
  await page.locator('.o_list_button_add, button:has-text("New")').first().click();
  await waitForOdooView(page);
  await fieldInput(page, "name").fill(`R6 Retention Policy ${r6}`);
  await beat(page, 300);
  await fieldInput(page, "code").fill(`R6_RETENTION_${r6}`);
  await beat(page, 300);
  await selectDropdownOption(page, "data_category", "Suppression History");
  await beat(page, 300);
  await fieldInput(page, "retention_period_days").fill("365");
  await beat(page, 600);
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);
  await beat(page, 1500);
  await page.locator('button:has-text("Preview Impact")').click();
  await beat(page, 600);
  await page.locator('.modal button:has-text("Preview")').click();
  await beat(page, 2000);

  // Legal hold placed on a specific recipient blocks a later erasure
  // request for that same recipient - the hold wins, not silently.
  const r6HeldPartnerId = await client.create("res.partner", {
    name: `R6 Held Subject ${r6}`,
    email: `r6.held.${r6}@example.com`,
  });
  const [heldReasonId] = await client.search("newsletter.suppression.reason", [
    ["code", "=", "MANUAL"],
  ]);
  await client.create("newsletter.suppression.entry", {
    partner_id: r6HeldPartnerId,
    scope: "global",
    reason_id: heldReasonId,
    source: "manual",
  });

  await switchUser(page, "demo.legal.hold", DEMO_PASSWORD);
  await page.goto("/odoo/newsletter.legal.hold/new");
  await waitForOdooView(page);
  await beat(page, 1200);
  await fieldInput(page, "name").fill(`R6 Pre-Erasure Hold ${r6}`);
  await beat(page, 300);
  await fieldInput(page, "reason").fill("Litigation preservation - blocks erasure for this recipient.");
  await beat(page, 300);
  await selectDropdownOption(page, "scope_type", "Recipient");
  await beat(page, 300);
  await page.locator('[name="scope_partner_ids"] input').first().fill(`R6 Held Subject ${r6}`);
  await page.waitForTimeout(700);
  await page.locator(".o-autocomplete--dropdown-menu li, .ui-menu-item").first().click();
  await beat(page, 500);
  await page.locator(".o_form_button_save, button[title='Save']").first().click();
  await waitForOdooView(page);
  await beat(page, 2000);

  const r6ErasureRequestId = await client.create("newsletter.privacy.request", {
    request_type: "erasure",
    requester: `R6 Held Subject ${r6}`,
    partner_id: r6HeldPartnerId,
  });

  await switchUser(page, "demo.privacy", DEMO_PASSWORD);
  await page.goto(`/odoo/newsletter.privacy.request/${r6ErasureRequestId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await fieldInput(page, "verification_method").fill("Email confirmation");
  await headerButton(page, "action_verify_identity_button").click();
  await waitForOdooView(page);
  await beat(page, 1200);
  await headerButton(page, "action_run_discovery").click();
  await waitForOdooView(page);
  await beat(page, 1500);
  await page.locator('.o_statusbar_buttons button:has-text("Execute")').click();
  await beat(page, 600);
  await page.locator('.modal button:has-text("Execute")').click();
  await waitForOdooView(page);
  await beat(page, 2200); // blocked by the legal hold - recorded, not silently ignored

  // Release the hold - a standing company/recipient hold would otherwise
  // affect every other retention/erasure check against this database.
  await switchUser(page, "demo.legal.hold", DEMO_PASSWORD);
  const [r6HoldId] = await client.search("newsletter.legal.hold", [
    ["name", "=", `R6 Pre-Erasure Hold ${r6}`],
  ]);
  await page.goto(`/odoo/newsletter.legal.hold/${r6HoldId}`);
  await waitForOdooView(page);
  await beat(page, 1200);
  await page.locator('button:has-text("Release Hold")').click();
  await beat(page, 500);
  await page.locator(".modal textarea").first().fill("Investigation closed - releasing for the walkthrough.");
  await beat(page, 700);
  await page.locator('.modal button:has-text("Release Hold")').last().click();
  await waitForOdooView(page);
  await beat(page, 1800);

  // Audit evidence export - a masked, hashed evidence package for the
  // archived campaign from R4, generated on demand.
  const auditExportId = await client.create("newsletter.audit.export", {
    export_type: "campaign",
    campaign_run_id: runId,
    purpose: "Platform walkthrough - compliance evidence package.",
  });
  await client.callKw("newsletter.audit.export", "action_generate_campaign_package", [[auditExportId]]);

  await switchUser(page, "demo.auditor", DEMO_PASSWORD);
  await gotoComplianceMenu(page, MENU.retentionActionLedger);
  await beat(page, 1800);
  await gotoComplianceMenu(page, MENU.privacyRequests);
  await beat(page, 1500);
  await gotoComplianceMenu(page, MENU.auditExports);
  await beat(page, 1500);
  await page.goto(`/odoo/newsletter.audit.export/${auditExportId}`);
  await waitForOdooView(page);
  await beat(page, 2500);
});
