import { expect, type Page } from "@playwright/test";
import { BASE_URL } from "./env";

/**
 * Navigates to the Email Marketing app and opens a Compliance submenu
 * item by its stable XML id (e.g.
 * "newsletter_compliance.menu_newsletter_dashboard") - matching it by
 * data-menu-xmlid rather than visible text, since several menu labels
 * repeat (e.g. two "Consent Purposes", two "Campaign Outcomes" entries
 * exist in the real menu tree) and xmlids never collide.
 */
export async function gotoComplianceMenu(page: Page, menuXmlId: string): Promise<void> {
  await page.goto(`${BASE_URL}/odoo/email-marketing`);
  await page.waitForSelector(".o_main_navbar", { timeout: 20000 });

  const complianceToggle = page.locator(
    '.o_main_navbar button:has(span[data-section]):has-text("Compliance")'
  );
  await complianceToggle.click();

  const link = page.locator(`a[data-menu-xmlid="${menuXmlId}"]`);
  await expect(link).toBeVisible({ timeout: 10000 });
  await link.click();
  await page.waitForLoadState("domcontentloaded");
  await waitForOdooView(page);
}

/** Waits for the Odoo SPA to finish rendering a view after navigation -
 * avoids relying on "networkidle", which never fires on Odoo's
 * long-lived bus/websocket connection. */
export async function waitForOdooView(page: Page): Promise<void> {
  await page.locator(".o_action_manager").waitFor({ state: "visible", timeout: 20000 });
  // A brief settle so in-flight XHRs populating the view have landed.
  await page.waitForTimeout(400);
}

/**
 * Locates the actual editable input/textarea for a form field. Odoo 19's
 * field widgets put the `name` attribute on the *wrapping* div
 * (`<div name="foo" class="o_field_widget">`), not on the inner
 * `<input>`/`<textarea>` itself - so `input[name="foo"]` never matches
 * anything. Use this everywhere a field needs to be filled.
 */
export function fieldInput(page: Page, fieldName: string) {
  return page.locator(`.o_field_widget[name="${fieldName}"] input, .o_field_widget[name="${fieldName}"] textarea`).first();
}

/**
 * Locates one statusbar option button, scoped to a specific field. Some
 * forms (mailing.mailing) carry two statusbar widgets whose values
 * overlap (both `state` and `compliance_state` have a "draft" option),
 * so a bare `.o_statusbar_status [data-value="draft"]` selector matches
 * two elements and trips Playwright's strict mode - always scope by
 * field name instead.
 */
export function statusbarOption(page: Page, fieldName: string, value: string) {
  return page.locator(`.o_field_widget[name="${fieldName}"] [data-value="${value}"]`);
}

/** Clicks a statusbar/header object button by its Python method name,
 * e.g. action_submit_content_review. */
export function headerButton(page: Page, methodName: string) {
  return page.locator(`.o_statusbar_buttons button[name="${methodName}"]`);
}

/** Clicks a header button that opens an action (wizard), addressed by
 * its visible text since those buttons carry a dynamic numeric action id
 * rather than a stable method name. */
export function headerActionButton(page: Page, visibleText: string) {
  return page.locator(`.o_statusbar_buttons button:has-text("${visibleText}")`);
}

/** A short pause for demo-recording pacing only - never used in the real
 * test suite, where speed/reliability matter more than watchability. */
export async function beat(page: Page, ms = 900): Promise<void> {
  await page.waitForTimeout(ms);
}

/**
 * Logs into Odoo through the real login form - used by the single-video
 * cross-role demo (demo/00-full-platform-e2e.demo.ts), which stays on one
 * continuous page/context for the whole recording rather than swapping
 * storageState contexts (each context would start its own separate video).
 */
export async function loginAs(page: Page, login: string, password: string): Promise<void> {
  await page.goto(`${BASE_URL}/web/login`);
  // Once more than one account has logged in on this same browser
  // context, Odoo's login page shows a "Choose a user" quick-switcher
  // (cached recent sessions, see web/static/src/core/user_switch) instead
  // of the username/password form - the form is still in the DOM the
  // whole time, just class="d-none" until "Use another user" is clicked.
  // A one-shot isVisible() check right after goto() is a race against
  // OWL mounting the component on the still-loading public website
  // template - retry the click itself instead of pre-checking visibility.
  await page
    .locator('button:has-text("Use another user")')
    .click({ timeout: 15000 })
    .catch(() => {}); // no quick-switcher shown (0 or 1 cached users) - the form is already visible
  await page.locator("#login").waitFor({ state: "visible", timeout: 15000 });
  await page.fill("#login", login);
  await page.fill("#password", password);
  await page.click('button:has-text("Log in")');
  await page.waitForURL(/\/odoo(\/|$)/, { timeout: 20000 });
}

/** Logs out and immediately logs back in as a different demo user, on the
 * same page/context - see loginAs() above. */
export async function switchUser(page: Page, login: string, password: string): Promise<void> {
  await page.goto(`${BASE_URL}/web/session/logout`);
  await loginAs(page, login, password);
}

export async function switchTopLevelAppMenu(page: Page): Promise<void> {
  await page.goto(`${BASE_URL}/odoo`);
  await page.waitForSelector(".o_main_navbar", { timeout: 20000 });
}

/**
 * Picks an option on an Odoo 19 Selection field. Odoo 19's Selection
 * field widget (web.SelectMenu) is NOT a native <select> - it's a
 * search/dropdown component, so a plain selectOption() call doesn't
 * apply. Opens the field's toggler, then clicks the dropdown item whose
 * visible text matches (the dropdown renders in a portal, not nested
 * under the field, hence searching the whole page for the open menu).
 */
export async function selectDropdownOption(
  page: Page,
  fieldName: string,
  optionText: string
): Promise<void> {
  const field = page.locator(`.o_field_widget[name="${fieldName}"]`);
  await field.locator(".o_select_menu_toggler, input").first().click();
  const menuItem = page
    .locator(".o_select_menu_item, .o-dropdown-item, .dropdown-item")
    .filter({ hasText: optionText })
    .first();
  await expect(menuItem).toBeVisible({ timeout: 10000 });
  await menuItem.click();
}
