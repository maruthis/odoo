import crypto from "crypto";
import { OdooClient } from "./odooClient";
import { ADMIN_LOGIN, ADMIN_PASSWORD, BASE_URL } from "./env";

const GENERIC_PROVIDER_SECRET = "playwright-demo-secret";

/** Configures the shared HMAC secret the generic provider adapter checks
 * incoming webhooks against (services/providers/generic_provider.py) -
 * idempotent, safe to call every run. Without this the webhook endpoint
 * fails closed and rejects every event (by design - see the adapter). */
export async function ensureGenericProviderSecret(client: OdooClient): Promise<void> {
  await client.callKw("ir.config_parameter", "set_param", [
    "newsletter_compliance.generic_provider_secret",
    GENERIC_PROVIDER_SECRET,
  ]);
}

/** Posts a signed delivery/bounce/complaint event straight at the real
 * webhook controller (controllers/event_webhook_controller.py), the same
 * way an actual SES/SendGrid/Mailgun callback would - HMAC-SHA256 over
 * the raw body, matching services/providers/generic_provider.py exactly.
 * Exercises the real authentication + normalization + ingestion path
 * rather than faking a provider_event record directly. */
export async function postProviderWebhookEvent(event: {
  provider_event_id?: string;
  provider_message_id?: string;
  event_type: string;
  event_timestamp?: string;
  email?: string;
  bounce_type?: string;
}): Promise<void> {
  const body = JSON.stringify(event);
  const signature =
    "sha256=" + crypto.createHmac("sha256", GENERIC_PROVIDER_SECRET).update(body).digest("hex");

  const res = await fetch(`${BASE_URL}/newsletter-compliance/v1/events/generic`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Newsletter-Signature": signature },
    body,
  });
  if (!res.ok) {
    throw new Error(`Provider webhook POST failed: ${res.status} ${await res.text()}`);
  }
}

/** A short random suffix so parallel test runs never collide on unique
 * codes (consent purpose code, brand code, campaign name). */
export function uniqueSuffix(): string {
  return `${Date.now()}${Math.floor(Math.random() * 1000)}`;
}

export interface CampaignFixture {
  purposeId: number;
  brandId: number;
  partnerId: number;
  partnerEmail: string;
  mailingId: number;
}

/** Returns an authenticated admin OdooClient, for use as a test fixture. */
export async function adminClient(): Promise<OdooClient> {
  const client = new OdooClient();
  await client.authenticate(ADMIN_LOGIN, ADMIN_PASSWORD);
  return client;
}

/**
 * Seeds one consent purpose, one brand, one consented recipient, and one
 * DRAFT campaign targeting that recipient - exactly the starting point
 * every governance-workflow test needs. Building this through the UI
 * would mean fighting the mailing body's rich-text/template builder for
 * no test value; the workflow buttons (Submit/Approve/Reject/Preflight/
 * Send) are what the UI tests actually exercise.
 */
export async function seedDraftCampaign(client: OdooClient, label: string): Promise<CampaignFixture> {
  const suffix = uniqueSuffix();

  // Owned by the demo Author, not by whichever account is doing the
  // seeding (admin) - otherwise later approve-as-admin calls would trip
  // the "campaign owner cannot approve their own content" self-approval
  // guard the same way they'd trip it for a real author.
  const [authorUserId] = await client.search("res.users", [["login", "=", "demo.author"]]);

  const purposeId = await client.create("newsletter.consent.purpose", {
    name: `E2E Purpose ${label} ${suffix}`,
    code: `E2E_PURPOSE_${suffix}`,
    privacy_notice_version: "v1",
  });

  const brandId = await client.create("newsletter.campaign.brand", {
    name: `E2E Brand ${label} ${suffix}`,
    code: `E2E_BRAND_${suffix}`,
    email_from: `e2e.${suffix}@example.com`,
    physical_address: "1 E2E Test Street",
    default_consent_purpose_id: purposeId,
  });

  const partnerEmail = `e2e.recipient.${suffix}@example.com`;
  const partnerId = await client.create("res.partner", {
    name: `E2E Recipient ${suffix}`,
    email: partnerEmail,
  });

  await client.create("newsletter.consent.record", {
    partner_id: partnerId,
    purpose_id: purposeId,
    status: "active",
    given_at: "2026-01-01 10:00:00",
    source: "website",
    channel: "web",
    privacy_notice_version: "v1",
  });

  const [partnerModelId] = await client.search("ir.model", [["model", "=", "res.partner"]]);

  const mailingId = await client.create("mailing.mailing", {
    name: `E2E Campaign ${label} ${suffix}`,
    subject: `E2E Subject ${label}`,
    mailing_type: "mail",
    mailing_model_id: partnerModelId,
    mailing_domain: JSON.stringify([["id", "in", [partnerId]]]),
    brand_id: brandId,
    consent_purpose_id: purposeId,
    email_from: `e2e.${suffix}@example.com`,
    body_html: `<p>E2E test content for ${label}</p>`,
    ...(authorUserId ? { business_owner_id: authorUserId } : {}),
  });

  return { purposeId, brandId, partnerId, partnerEmail, mailingId };
}

/** Advances a fixture's campaign through content + compliance approval
 * and preflight, so it lands on "Ready to Send" - the common starting
 * point for Campaign Operator tests. Done via RPC using the *actual*
 * governance methods (not by writing compliance_state directly), so the
 * same server-side validation the UI tests exercise elsewhere still ran -
 * this is a shortcut for getting to the starting line, not a bypass of
 * the workflow logic itself.
 */
/**
 * Runs a scheduled action immediately, the same way "Run Manually" does
 * in Settings -> Technical -> Scheduled Actions. Cron *methods* on the
 * model itself are private (underscore-prefixed) and Odoo 19 refuses to
 * call them directly over RPC ("Private methods ... cannot be called
 * remotely") - triggering the ir.cron record's own public
 * method_direct_trigger() is the supported way to run one synchronously
 * from outside the UI.
 */
/**
 * Temporarily disables a cron for the duration of `fn()`, then always
 * re-enables it. Used only where a test needs to deterministically
 * outrun the *live dev server's own* real 1-minute dispatch cron (which
 * keeps running against the same database this suite uses) - e.g.
 * cancelling a just-started execution before it can auto-complete.
 * Restores the cron's previous active state even if `fn()` throws.
 */
export async function withCronPaused<T>(
  client: OdooClient,
  cronXmlId: string,
  fn: () => Promise<T>
): Promise<T> {
  const [cronId] = await client.resolveXmlIds([cronXmlId]);
  await client.write("ir.cron", [cronId], { active: false });
  try {
    return await fn();
  } finally {
    await client.write("ir.cron", [cronId], { active: true });
  }
}

export async function triggerCron(client: OdooClient, cronXmlId: string): Promise<void> {
  const [cronId] = await client.resolveXmlIds([cronXmlId]);
  try {
    await client.callKw("ir.cron", "method_direct_trigger", [[cronId]]);
  } catch (err: any) {
    // The live dev server has this same cron on its own 1-minute
    // schedule, so a run already in progress there is a benign race, not
    // a real failure - callers poll for the expected outcome afterward
    // instead of assuming this call itself was synchronous.
    if (!String(err?.message || "").includes("already executing")) {
      throw err;
    }
  }
}

/** Polls `fn()` until `predicate` is satisfied or `timeoutMs` elapses.
 * Used after triggerCron(), since a cron trigger can't be assumed
 * synchronous (see triggerCron's catch above). */
export async function pollUntil<T>(
  fn: () => Promise<T>,
  predicate: (value: T) => boolean,
  timeoutMs = 20_000,
  intervalMs = 500
): Promise<T> {
  const start = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const value = await fn();
    if (predicate(value)) return value;
    if (Date.now() - start > timeoutMs) {
      throw new Error(`pollUntil timed out after ${timeoutMs}ms`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

/**
 * Nudges the dispatch cron until a run archives, forcing any retry
 * backoff to clear immediately along the way. This dev environment has
 * no real outgoing SMTP relay, so a send attempt commonly fails and
 * schedules a retry ~60s+ out (exponential base_retry_delay_seconds
 * backoff) - waiting on that for real would make tests slow and flaky.
 * Whether the recipient's send ultimately succeeds or exhausts its
 * retries and reconciles as completed-with-errors, the run still
 * archives either way - that's all callers need.
 */
export async function driveRunToArchive(
  client: OdooClient,
  cronXmlId: string,
  runId: number,
  maxAttempts = 8
): Promise<any> {
  let run: any;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await triggerCron(client, cronXmlId);
    await new Promise((resolve) => setTimeout(resolve, 1000));

    const [current] = await client.callKw<any[]>("newsletter.campaign.run", "read", [
      [runId],
      ["state", "archive_id", "sent_count"],
    ]);
    run = current;
    if (run.archive_id) return run;

    const retryPendingIds = await client.search("newsletter.recipient.eligibility", [
      ["campaign_run_id", "=", runId],
      ["dispatch_state", "=", "retry_pending"],
    ]);
    if (retryPendingIds.length) {
      await client.write("newsletter.recipient.eligibility", retryPendingIds, {
        next_retry_at: false,
      });
    }
  }
  return run;
}

export async function advanceToReadyToSend(client: OdooClient, mailingId: number): Promise<void> {
  await client.callKw("mailing.mailing", "action_submit_content_review", [[mailingId]]);
  await client.callKw("mailing.mailing", "action_approve_content", [[mailingId]]);
  await client.callKw("mailing.mailing", "action_approve_compliance", [[mailingId]]);
  await client.callKw("mailing.mailing", "action_run_compliance_preflight", [[mailingId]]);
}
