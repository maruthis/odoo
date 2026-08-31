# Odoo

[![Build Status](https://runbot.odoo.com/runbot/badge/flat/1/master.svg)](https://runbot.odoo.com/runbot)
[![Tech Doc](https://img.shields.io/badge/master-docs-875A7B.svg?style=flat&colorA=8F8F8F)](https://www.odoo.com/documentation/master)
[![Help](https://img.shields.io/badge/master-help-875A7B.svg?style=flat&colorA=8F8F8F)](https://www.odoo.com/forum/help-1)
[![Nightly Builds](https://img.shields.io/badge/master-nightly-875A7B.svg?style=flat&colorA=8F8F8F)](https://nightly.odoo.com/)

## Bulk Email Compliance Solution (this workspace)

This checkout also carries a compliant bulk-email platform for MedhAnkura and Techsophy, built entirely on **Odoo 19 Community Edition** — no separate integration stack, no additional infrastructure.

**How the solution is assembled:**

| Layer | Source | Role |
|---|---|---|
| Campaign creation & sending | Odoo CE's stock **Email Marketing** app (`addons/mass_mailing`) | Content authoring, recipient lists, the native mailing send/queue engine |
| Compliance governance | `custom-addons/newsletter_compliance/` (our module) | Consent & suppression, approval workflow, preflight eligibility, execution ledger & immutable archive, delivery feedback/monitoring, privacy & retention lifecycle |

The custom module extends `mass_mailing.mailing` rather than replacing it — every campaign is still an ordinary Odoo mailing; `newsletter_compliance` adds a parallel `compliance_state` that gates whether it's allowed to send, plus the models, screens, and audit trail described below.

**What it delivers**, built in six phases (see `mydocs/Custom Module R1.md`–`R6.md`):

1. **Foundation** — consent records, consent purposes, and a suppression register (bounce/complaint/unsubscribe/manual).
2. **Campaign Governance** — content-review and compliance-review approval chain before anything can send.
3. **Preflight & Eligibility** — the recipient list is checked against consent and suppression, then frozen.
4. **Execution & Archive** — throttled, resumable sending with a locked, tamper-evident archive of every campaign as sent.
5. **Delivery Feedback & Monitoring** — an authenticated webhook ingests bounce/complaint events and auto-suppresses affected addresses, with threshold alerts.
6. **Privacy & Retention** — data subject access/erasure requests, configurable retention policies, and legal holds.

**Where to look:**

- `custom-addons/newsletter_compliance/` — the module itself (models, views, security, services, tests).
- `testautomation/` — a Playwright E2E suite (42 tests across all 9 roles) plus a demo-recording suite (`npm run demo`) that produces one video per role and one full R1–R6 walkthrough.
- `mydocs/` — the business requirements, the R1–R6 design docs, and `mydocs/user guide/Newsletter Compliance User Guide.html`, a role-based, screenshot-illustrated guide for every role from Newsletter Author through Compliance Audit Reviewer.
- `run.sh` / `docker-compose.yml` / `odoo.dev.conf` — local dev server setup (Postgres via Docker, then `./run.sh` to launch Odoo).

---

Odoo is a suite of web based open source business apps.

The main Odoo Apps include an [Open Source CRM](https://www.odoo.com/page/crm),
[Website Builder](https://www.odoo.com/app/website),
[eCommerce](https://www.odoo.com/app/ecommerce),
[Warehouse Management](https://www.odoo.com/app/inventory),
[Project Management](https://www.odoo.com/app/project),
[Billing &amp; Accounting](https://www.odoo.com/app/accounting),
[Point of Sale](https://www.odoo.com/app/point-of-sale-shop),
[Human Resources](https://www.odoo.com/app/employees),
[Marketing](https://www.odoo.com/app/social-marketing),
[Manufacturing](https://www.odoo.com/app/manufacturing),
[...](https://www.odoo.com/)

Odoo Apps can be used as stand-alone applications, but they also integrate seamlessly so you get
a full-featured [Open Source ERP](https://www.odoo.com) when you install several Apps.

## Getting started with Odoo

For a standard installation please follow the [Setup instructions](https://www.odoo.com/documentation/master/administration/install/install.html)
from the documentation.

To learn the software, we recommend the [Odoo eLearning](https://www.odoo.com/slides),
or [Scale-up, the business game](https://www.odoo.com/page/scale-up-business-game).
Developers can start with [the developer tutorials](https://www.odoo.com/documentation/master/developer/howtos.html).

## Security

If you believe you have found a security issue, check our [Responsible Disclosure page](https://www.odoo.com/security-report)
for details and get in touch with us via email.
