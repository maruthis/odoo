/** Demo recording - Newsletter Author (Demo Playbook §3.1). */
import { test } from "@playwright/test";
import { adminClient, seedDraftCampaign } from "../src/seedData";
import { beat, gotoComplianceMenu, headerActionButton, headerButton, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

test("Newsletter Author walkthrough", async ({ page }) => {
  const client = await adminClient();
  const fixture = await seedDraftCampaign(client, "demo-author");

  // My Campaigns - see the draft.
  await gotoComplianceMenu(page, MENU.myCampaigns);
  await beat(page, 1500);

  // Open it.
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);
  await beat(page, 1500);

  // Submit for content review.
  await headerButton(page, "action_submit_content_review").click();
  await waitForOdooView(page);
  await beat(page, 2000);

  // Show a second draft the Author decides not to proceed with, and
  // cancels it instead.
  const second = await seedDraftCampaign(client, "demo-author-cancel");
  await page.goto(`/odoo/mailing.mailing/${second.mailingId}`);
  await waitForOdooView(page);
  await beat(page, 1200);

  await headerActionButton(page, "Cancel Campaign").click();
  await page.locator(".modal textarea").first().fill("No longer needed - superseded by a newer draft.");
  await beat(page, 800);
  await page
    .locator('.modal button:has-text("Cancel Campaign"), .modal button:has-text("Confirm")')
    .first()
    .click();
  await waitForOdooView(page);
  await beat(page, 2000);
});
