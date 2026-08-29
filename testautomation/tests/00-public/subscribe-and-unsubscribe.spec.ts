/**
 * Functionality Playbook §16 (Public Consent Collection & Double Opt-In)
 * and §15 (Unsubscribe Flow). Both are plain `auth="public"` HTTP
 * controllers - no Odoo login required, matching how a real recipient
 * would reach them.
 */
import { expect, test } from "@playwright/test";
import {
  adminClient,
  advanceToReadyToSend,
  pollUntil,
  seedDraftCampaign,
  triggerCron,
  uniqueSuffix,
} from "../../src/seedData";
import { OdooClient } from "../../src/odooClient";

test.describe("Public subscribe page - double opt-in", () => {
  let client: OdooClient;
  let purposeId: number;
  let purposeName: string;

  test.beforeEach(async () => {
    client = await adminClient();
    const suffix = uniqueSuffix();
    purposeName = `Public Subscribe Purpose ${suffix}`;
    purposeId = await client.create("newsletter.consent.purpose", {
      name: purposeName,
      code: `PUBLIC_SUB_${suffix}`,
      privacy_notice_version: "v1",
      public_subscribe: true,
    });
  });

  test("subscribe form lists the public purpose", async ({ page }) => {
    await page.goto("/newsletter-compliance/subscribe");
    await expect(page.locator("h2")).toHaveText("Newsletter Subscription");
    await expect(page.locator(`text=${purposeName}`)).toBeVisible();
  });

  test("submitting without the consent checkbox is rejected", async ({ page }) => {
    await page.goto("/newsletter-compliance/subscribe");
    await page.fill('input[name="email"]', `no.consent.${uniqueSuffix()}@example.com`);
    const checkbox = page.locator(`input[name="purpose_ids"][value="${purposeId}"]`);
    await checkbox.check();
    const response = await page.request.post("/newsletter-compliance/subscribe", {
      form: { email: `no.consent.${uniqueSuffix()}@example.com`, purpose_ids: String(purposeId) },
    });
    expect(response.status()).toBe(400);
  });

  test("full double opt-in flow: submit, pending, confirm, active", async ({ page }) => {
    const email = `subscriber.${uniqueSuffix()}@example.com`;

    await page.goto("/newsletter-compliance/subscribe");
    await page.fill('input[name="email"]', email);
    await page.fill('input[name="first_name"]', "Playwright");
    await page.fill('input[name="last_name"]', "Subscriber");
    await page.locator(`input[name="purpose_ids"][value="${purposeId}"]`).check();
    await page.locator('input[name="consent"]').check();
    await page.locator('button:has-text("Subscribe")').click();

    await expect(page.locator("h2")).toHaveText("Almost done");
    await expect(page.locator(`text=${email}`)).toBeVisible();

    // Read the pending consent record back via RPC - confirms the public
    // page actually persisted a PENDING (not active) record server-side.
    const [consentId] = await client.search("newsletter.consent.record", [
      ["email_normalized", "=", email],
    ]);
    expect(consentId).toBeTruthy();
    const [consent] = await client.callKw<any[]>("newsletter.consent.record", "read", [
      [consentId],
      ["status", "confirmation_token", "given_at"],
    ]);
    expect(consent.status).toBe("pending");
    expect(consent.given_at).toBe(false);
    expect(consent.confirmation_token).toBeTruthy();

    await page.goto(`/newsletter-compliance/subscribe/confirm/${consent.confirmation_token}`);
    await expect(page.locator("h2")).toHaveText("Subscription confirmed");
    await expect(page.locator(`text=${purposeName}`)).toBeVisible();

    const [confirmed] = await client.callKw<any[]>("newsletter.consent.record", "read", [
      [consentId],
      ["status", "given_at"],
    ]);
    expect(confirmed.status).toBe("active");
    expect(confirmed.given_at).toBeTruthy();
  });

  test("confirming an already-used token shows the invalid/used message", async ({ page }) => {
    const email = `reused.token.${uniqueSuffix()}@example.com`;
    await page.goto("/newsletter-compliance/subscribe");
    await page.fill('input[name="email"]', email);
    await page.locator(`input[name="purpose_ids"][value="${purposeId}"]`).check();
    await page.locator('input[name="consent"]').check();
    await page.locator('button:has-text("Subscribe")').click();

    const [consentId] = await client.search("newsletter.consent.record", [
      ["email_normalized", "=", email],
    ]);
    const [consent] = await client.callKw<any[]>("newsletter.consent.record", "read", [
      [consentId],
      ["confirmation_token"],
    ]);

    await page.goto(`/newsletter-compliance/subscribe/confirm/${consent.confirmation_token}`);
    await expect(page.locator("h2")).toHaveText("Subscription confirmed");

    const secondAttempt = await page.request.get(
      `/newsletter-compliance/subscribe/confirm/${consent.confirmation_token}`
    );
    expect(secondAttempt.status()).toBe(400);
  });
});

test.describe("Public unsubscribe page", () => {
  test("an invalid/tampered token is rejected", async ({ page }) => {
    const response = await page.request.get("/newsletter-compliance/unsubscribe/not-a-real-token");
    expect(response.status()).toBe(400);
  });

  test("clicking the unsubscribe link embedded in a real send suppresses the recipient", async ({
    page,
  }) => {
    const client = await adminClient();
    const fixture = await seedDraftCampaign(client, "unsub-link");
    await advanceToReadyToSend(client, fixture.mailingId);

    const [mailing] = await client.callKw<any[]>("mailing.mailing", "read", [
      [fixture.mailingId],
      ["current_campaign_run_id"],
    ]);
    const runId = mailing.current_campaign_run_id[0];
    await client.callKw("newsletter.campaign.run", "action_start_execution", [[runId]]);
    // The dispatch cron normally does this on a schedule (and the live
    // dev server has it too) - trigger it as a best-effort nudge, then
    // poll for the mail.mail it produces rather than assuming the
    // trigger call itself was synchronous.
    await triggerCron(client, "newsletter_compliance.ir_cron_newsletter_dispatch_worker");

    const [mailRecordId] = await pollUntil(
      () => client.search("mail.mail", [["email_to", "=", fixture.partnerEmail]], {
        order: "id desc",
        limit: 1,
      }),
      (ids) => ids.length > 0
    );
    expect(mailRecordId, "expected a mail.mail record for the dispatched recipient").toBeTruthy();

    const [mailRecord] = await client.callKw<any[]>("mail.mail", "read", [
      [mailRecordId],
      ["body_html"],
    ]);
    const match = /href="([^"]*\/newsletter-compliance\/unsubscribe\/[^"]+)"/.exec(
      mailRecord.body_html
    );
    expect(match, "expected an unsubscribe link in the sent email body").toBeTruthy();
    const unsubscribeUrl = match![1];

    await page.goto(unsubscribeUrl);
    await expect(page.locator("h2")).toHaveText("Manage your email preferences");

    await page.locator('input[name="choice"][value="all"]').check();
    await page.locator('button:has-text("Confirm")').click();
    await expect(page.locator("h2")).toHaveText("You have been unsubscribed.");

    const suppressionIds = await client.search("newsletter.suppression.entry", [
      ["partner_id", "=", fixture.partnerId],
      ["scope", "=", "global"],
    ]);
    expect(suppressionIds.length).toBeGreaterThan(0);

    const blacklisted = await client.search("mail.blacklist", [
      ["email", "=", fixture.partnerEmail],
    ]);
    expect(blacklisted.length).toBeGreaterThan(0);
  });
});
