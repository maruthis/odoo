# Newsletter Compliance - Playwright E2E Suite

End-to-end browser tests for the `newsletter_compliance` Odoo module, driven directly by:

- `mydocs/Newsletter Compliance Demo Playbook.md` - the role-based structure (one spec file per role, `01`-`09`), plus the flagship cross-role lifecycle test (`10`).
- `mydocs/Odoo CE Bulk Email Functionality Playbook.md` - the public-facing functionality (`00-public`): the subscribe/double-opt-in flow and the unsubscribe flow, neither of which requires a logged-in Odoo user.

## Prerequisites

- The Odoo dev server running locally with the `newsletter_compliance` module installed (`./run.sh -d odoo19`, from the repo root).
- Node.js 18+.

## Setup

```bash
cd testautomation
npm install
npx playwright install chromium
```

## Running

```bash
npx playwright test              # headless, all projects
npx playwright test --headed     # watch it click through the UI
npx playwright test --ui         # Playwright's interactive UI mode
npx playwright test tests/05-campaign-operator.spec.ts   # one spec
npx playwright show-report       # HTML report from the last run
```

Every run's `globalSetup` (`global-setup.ts`) automatically:

1. Idempotently creates the 9 demo users from the Demo Playbook's Appendix A (`demo.author`, `demo.approver`, `demo.reviewer`, `demo.compliance.admin`, `demo.operator`, `demo.ops.admin`, `demo.privacy`, `demo.legal.hold`, `demo.auditor` - all sharing the password in `src/env.ts`), each holding exactly the one role its name implies, plus the base groups needed to see the Email Marketing app at all.
2. Grants the `admin` user Compliance Administrator too, since `admin` is also used (via RPC only, never through the UI assertions) as the account that seeds and advances test fixtures - see "How test data is created" below.
3. Logs in as `admin` and as each of the 9 demo users through the real login page, and saves each session's storage state to `.auth/<role>.json` - one login per role per run, then every test in that role's spec file reuses the saved session instead of re-logging-in per test.

## How test data is created

Campaign *content* creation goes through `mass_mailing`'s own rich-text/theme builder, which is stock Odoo UI, not `newsletter_compliance` code - clicking through it wouldn't be testing anything this module owns, and it's a notoriously brittle thing to automate reliably. So test fixtures (consent purposes, brands, consented contacts, draft campaigns) are seeded via a small JSON-RPC client (`src/odooClient.ts`, `src/seedData.ts`), authenticated as `admin`, before each test that needs one.

Every *assertion* still goes through the real browser, logged in as the actual role being tested, clicking the actual workflow buttons (`Submit for Content Review`, `Approve Content`, `Approve Compliance`, `Run Compliance Preflight`, `Send`, `Reinstate`, `Release Hold`, `Verify Integrity`, ...) - this is what the suite is actually testing: the custom governance workflow, permissions, and state machine this module adds on top of stock Odoo, not Odoo's own mailing editor.

`src/seedData.ts` exposes `advanceToReadyToSend()`, which calls the same governance model methods (`action_submit_content_review`, `action_approve_content`, `action_approve_compliance`, `action_run_compliance_preflight`) via RPC rather than writing `compliance_state` directly - so even the "get to the starting line" shortcut still runs the real server-side validation, it just skips clicking through screens a given test isn't about.

## Demo recordings

Beyond the pass/fail test suite above, `npm run demo` produces:

- **One watchable video per role** (`01`-`09`) - a single continuous walkthrough of that role's key actions from the Demo Playbook, no on-screen banners, just the raw UI.
- **One comprehensive video** (`00-full-platform-e2e`) - a single continuous recording covering every requirement phase R1 through R6 from `mydocs/Custom Module R1.md`-`R6.md` (consent/suppression foundation -> campaign governance -> preflight/eligibility -> execution/archive -> delivery feedback/monitoring -> privacy/retention/legal hold/evidence export), switching between all 9 roles by logging in and out through the real login form rather than swapping browser contexts (a new context would start a separate video, defeating the point of one continuous recording).

```bash
npm run demo          # records all 10 videos, then collects them
npm run demo:report   # HTML report (with embedded video per test) from the last demo run
```

This uses a separate config, `playwright.demo.config.ts`, kept apart from `playwright.config.ts` on purpose: the main suite is tuned for fast, reliable assertions (parallel workers, video only on failure); the demo config is tuned for one continuous, watchable recording per project (`workers: 1`, `fullyParallel: false`, `video: "on"`, a larger 1600x1000 viewport). The 9 per-role projects reuse `global-setup.ts`'s auth states like the main suite; `00-full-platform-e2e` starts logged out on purpose and drives its own logins.

Each `demo/<NN>-<role>.demo.ts` file is a single `test()` adapted from that role's numbered spec file in `tests/`, merging several test cases into one narrative flow and inserting `beat()` pauses (`src/nav.ts`) so the recording is watchable rather than instant - `beat()` exists solely for this purpose and is never used in the real test suite. `demo/00-full-platform-e2e.demo.ts` is the exception: it isn't adapted from one spec file, it walks through R1-R6 end to end, reusing the same seed/nav helpers throughout.

`demo/00-full-platform-e2e.demo.ts` also exercises the real delivery-feedback webhook (`src/seedData.ts`'s `ensureGenericProviderSecret()` / `postProviderWebhookEvent()`): it configures the generic provider's shared HMAC secret, then POSTs a real signed hard-bounce event at `controllers/event_webhook_controller.py` the same way SES/SNS would, and lets the real authentication -> correlation -> classification -> automatic-suppression pipeline run - the only faked piece is the provider message id itself (written directly onto the recipient eligibility row), since this dev environment has no outgoing SMTP relay to ever produce a real one. This is also how a real bug was found and fixed in `models/provider_event.py`'s `_parse_event_timestamp()`: a timezone-aware ISO timestamp with a trailing "Z" (exactly what AWS SNS/SES actually send) crashed ingestion with `ValueError: Datetime field expects a naive datetime` - it now normalizes to naive UTC first.

Playwright writes raw videos into per-test hashed directories under `demo-recordings/.raw/`; `npm run demo` automatically runs `demo/collect-videos.js` afterward to copy each one into a clean, discoverable name alongside it, e.g. `demo-recordings/05-campaign-operator.webm`. `demo-recordings/` is gitignored (large binaries) - treat it as local output, not something to commit.

## Structure

```
testautomation/
├── global-setup.ts        # demo user provisioning + storageState capture
├── playwright.config.ts    # one project per role, mapped to its spec file + storageState
├── src/
│   ├── env.ts               # base URL, demo user/role definitions
│   ├── odooClient.ts         # minimal JSON-RPC client for fixture setup
│   ├── seedUsers.ts          # idempotent demo user provisioning
│   ├── seedData.ts           # campaign/consent/suppression fixture helpers
│   ├── nav.ts                 # menu navigation + statusbar/header button helpers
│   └── menuIds.ts              # data-menu-xmlid constants (one source of truth)
└── tests/
    ├── 00-public/                          # no login required
    │   └── subscribe-and-unsubscribe.spec.ts
    ├── 01-newsletter-author.spec.ts
    ├── 02-content-approver.spec.ts
    ├── 03-compliance-reviewer.spec.ts
    ├── 04-compliance-administrator.spec.ts
    ├── 05-campaign-operator.spec.ts
    ├── 06-operations-administrator.spec.ts
    ├── 07-privacy-officer.spec.ts
    ├── 08-legal-hold-administrator.spec.ts
    ├── 09-compliance-audit-reviewer.spec.ts
    └── 10-end-to-end-lifecycle.spec.ts       # the full cross-role handoff + a hold-blocks-erasure scenario

demo/                       # video recordings - one per role, plus a comprehensive R1-R6 one (see "Demo recordings" above)
├── collect-videos.js         # copies raw per-test videos into clean demo-recordings/<name>.webm names
├── 00-full-platform-e2e.demo.ts   # single continuous R1-R6 walkthrough, all 9 roles, real logins
├── 01-author.demo.ts
├── 02-content-approver.demo.ts
├── ...
└── 09-compliance-audit-reviewer.demo.ts
```

## Notes

- Menu navigation is done via `a[data-menu-xmlid="..."]` rather than visible text, because several menu labels repeat in the real menu tree (e.g. two separate "Consent Purposes" entries, two "Campaign Outcomes" entries) - xmlids never collide. `src/menuIds.ts` is the single place these are kept, matching `views/menu_views.xml`.
- `waitForOdooView()` in `src/nav.ts` deliberately avoids Playwright's `networkidle` wait condition - Odoo's SPA keeps a long-lived bus/websocket connection open, so `networkidle` never actually fires.
- These tests run against a real dev database and create real records (prefixed `E2E_`/`PW_`/`Playwright:` throughout for easy identification) - point `ODOO_BASE_URL`/`ODOO_DB` env vars at a disposable database, not a database anyone cares about.
- Any test that creates a **company-wide legal hold** releases it before finishing (a standing company-wide hold blocks retention/erasure for every record in the database, including other suites' fixtures - this bit the Python test suite once during development, see `tests/08-legal-hold-administrator.spec.ts`). If a run is interrupted mid-test, an unreleased hold can be left behind - check `newsletter.legal.hold` for `status = 'active', scope_type = 'company'` and release manually via the UI or `action_release()` if the Python suite starts failing retention/erasure assertions unexpectedly.
- `src/seedData.ts`'s `driveRunToArchive()` exists because this dev environment has no real outgoing SMTP relay - a dispatch attempt commonly fails and schedules a retry with exponential backoff, so it forces each retry immediately eligible again after every cron nudge rather than waiting on real backoff timing.
- Once more than one account has logged in within the same browser context, Odoo's `/web/login` page shows a "Choose a user" quick-switcher (cached recent sessions, `web/static/src/core/user_switch`) instead of the username/password form - the form is still in the DOM the whole time, just `class="d-none"` until "Use another user" is clicked. `src/nav.ts`'s `loginAs()`/`switchUser()` (used only by `demo/00-full-platform-e2e.demo.ts`, which stays on one page/context across all 9 role switches) handle this by attempting that click every time and swallowing the "not found" case rather than pre-checking visibility, which raced against OWL mounting the component.
