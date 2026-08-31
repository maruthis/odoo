/**
 * Verifies the click/open tracking fix in services/dispatch_service.py:
 * a real click on a link inside a sent campaign should move
 * mailing.mailing's native "Clicked"/"Opened" stats off zero (they
 * previously could never move, since our dispatch path bypassed
 * mass_mailing's own send pipeline entirely - see dispatch_service.py's
 * module docstring), and the stat buttons that surface those numbers
 * (gated on mailing.state, not our own compliance_state) should become
 * visible once the campaign has actually sent - campaign_run.py's
 * action_start_execution()/_reconcile_and_finalize_if_complete() now
 * keep that field in sync specifically so they do.
 */
import { expect, test } from "@playwright/test";
import {
  adminClient,
  advanceToReadyToSend,
  pollUntil,
  seedDraftCampaign,
  triggerCron,
} from "../src/seedData";
import { waitForOdooView } from "../src/nav";

test("a real click on a sent campaign's link increments Clicked/Opened and reveals the native stat buttons", async ({
  page,
}) => {
  const client = await adminClient();
  const fixture = await seedDraftCampaign(client, "click-tracking");

  // A real link to click - seedDraftCampaign's default body has none.
  await client.write("mailing.mailing", [fixture.mailingId], {
    body_html: '<p>Visit <a href="https://example.com/landing-page">our landing page</a></p>',
  });

  await advanceToReadyToSend(client, fixture.mailingId);

  const [mailingBeforeSend] = await client.callKw<any[]>("mailing.mailing", "read", [
    [fixture.mailingId],
    ["current_campaign_run_id"],
  ]);
  const runId = mailingBeforeSend.current_campaign_run_id[0];
  await client.callKw("newsletter.campaign.run", "action_start_execution", [[runId]]);
  await triggerCron(client, "newsletter_compliance.ir_cron_newsletter_dispatch_worker");

  // send_recipient() creates the mailing.trace inline with the mail.mail
  // it sends - poll rather than assume the cron trigger was synchronous.
  const [traceId] = await pollUntil(
    () => client.search("mailing.trace", [["mass_mailing_id", "=", fixture.mailingId]]),
    (ids) => ids.length > 0
  );

  const [linkTrackerId] = await client.search("link.tracker", [
    ["mass_mailing_id", "=", fixture.mailingId],
  ]);
  expect(
    linkTrackerId,
    "expected convert_links() to have created a link.tracker for the body's link"
  ).toBeTruthy();
  const [linkTracker] = await client.callKw<any[]>("link.tracker", "read", [
    [linkTrackerId],
    ["code"],
  ]);

  // The exact same public redirect a recipient's own click hits - no
  // login, no page navigation, just the real click-tracking endpoint.
  // maxRedirects: 0 so this doesn't depend on example.com actually
  // responding, only on Odoo's own redirect being issued.
  const clickResponse = await page.request.get(`/r/${linkTracker.code}/m/${traceId}`, {
    maxRedirects: 0,
  });
  expect([301, 302]).toContain(clickResponse.status());

  const [statsAfterClick] = await pollUntil(
    () => client.callKw<any[]>("mailing.mailing", "read", [[fixture.mailingId], ["clicked", "opened"]]),
    ([mailing]) => mailing.clicked === 1
  );
  expect(statsAfterClick.clicked).toBe(1);
  // A click always counts as an open too (mass_mailing's own
  // link.tracker.click.add_click() override calls both).
  expect(statsAfterClick.opened).toBe(1);

  // UI check: the native stat buttons are invisible while
  // mailing.state == 'draft' - action_start_execution() now advances it,
  // so they should be visible on a campaign that has actually sent.
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);
  await expect(page.locator('button[name="action_view_clicked"]')).toBeVisible();
  await expect(page.locator('button[name="action_view_opened"]')).toBeVisible();
});
