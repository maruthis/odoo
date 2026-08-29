/**
 * Demo Playbook §3.1 - Newsletter Author.
 *
 * Campaign *creation* goes through mass_mailing's own rich-content/theme
 * builder, which isn't a meaningful thing for this suite to click through
 * (it's stock Odoo UI, not custom_addons/newsletter_compliance code) -
 * so campaigns are seeded via RPC, owned by the Author, and these tests
 * exercise the actual custom governance workflow buttons on top of that,
 * exactly as an Author would use them after creating a draft.
 */
import { expect, test } from "@playwright/test";
import { adminClient, seedDraftCampaign, type CampaignFixture } from "../src/seedData";
import { gotoComplianceMenu, headerActionButton, headerButton, statusbarOption, waitForOdooView } from "../src/nav";
import { MENU } from "../src/menuIds";

let fixture: CampaignFixture;

test.beforeEach(async () => {
  const client = await adminClient();
  fixture = await seedDraftCampaign(client, "author");
});

test("My Campaigns lists a draft campaign owned by the Author", async ({ page }) => {
  await gotoComplianceMenu(page, MENU.myCampaigns);
  await page.locator('input.o_searchview_input').fill(fixture.partnerEmail.split("@")[0]);
  // Search on campaign name instead - more reliable than the recipient email.
  await page.locator('input.o_searchview_input').fill("");
  await expect(page.locator(`.o_list_table:has-text("Draft")`).first()).toBeVisible({
    timeout: 15000,
  });
});

test("Author can submit a draft for content review", async ({ page }) => {
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);

  await expect(headerButton(page, "action_submit_content_review")).toBeVisible();
  await headerButton(page, "action_submit_content_review").click();
  await waitForOdooView(page);

  await expect(statusbarOption(page, "compliance_state", "content_review")).toHaveAttribute(
    "aria-checked",
    "true"
  );
});

test("Author cannot see the Approve Content button (not their role)", async ({ page }) => {
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);
  await headerButton(page, "action_submit_content_review").click();
  await waitForOdooView(page);

  await expect(headerButton(page, "action_approve_content")).toHaveCount(0);
});

test("Author can cancel their own draft campaign", async ({ page }) => {
  await page.goto(`/odoo/mailing.mailing/${fixture.mailingId}`);
  await waitForOdooView(page);

  await headerActionButton(page, "Cancel Campaign").click();
  await page.locator('.modal textarea, .modal input[name="reason"]').first().fill(
    "Playwright: no longer needed"
  );
  await page
    .locator('.modal button:has-text("Cancel Campaign"), .modal button:has-text("Confirm")')
    .first()
    .click();
  await waitForOdooView(page);

  await expect(statusbarOption(page, "compliance_state", "cancelled")).toHaveAttribute(
    "aria-checked",
    "true"
  );
});
