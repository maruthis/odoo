Absolutely. For **R1 — Foundation**, I would build only the compliance primitives and security model. We will **not yet modify the send workflow** or implement preflight; those belong in R2/R3.

R1 directly prepares for the source requirements around valid consent, suppression, recipient-level traceability, restricted access, and retention. The specification requires recipients without valid consent to be excluded, suppression to cover bounce/complaint/unsubscribe cases, and access to consent/suppression data to be restricted and logged.

For Odoo 19, the normal custom-module pattern remains Python models plus XML/CSV data files, with ACLs through `ir.model.access` and finer restrictions through record rules. Odoo also warns that ACLs are additive and record rules need careful composition, which matters for our role design. ([Odoo](https://www.odoo.com/documentation/19.0/developer/tutorials/backend.html?utm_source=chatgpt.com "Building a Module — Odoo 19.0 documentation"))

# R1 — Newsletter Compliance Foundation

## 1\. R1 scope

R1 should deliver these capabilities:

| Capability | R1 |
| --- | --- |
| Consent Purpose Master | ✅ |
| Consent Register | ✅ |
| Consent history | ✅ |
| Consent withdrawal | ✅ |
| Suppression Register | ✅ |
| Scoped suppression | ✅ |
| Suppression reason master | ✅ |
| Contact compliance summary | ✅ |
| Security roles | ✅ |
| Multi-company segregation | ✅ |
| Chatter/audit tracking | ✅ |
| Standard blacklist synchronization | ✅ Basic |
| Campaign workflow | R2 |
| Campaign approvals | R2 |
| Recipient preflight | R3 |
| Send blocking | R3 |
| Delivery event ledger | R4 |
| Immutable campaign archive | R4 |

* * *

# 2\. Module

Create:

    newsletter_compliance

Directory:

    newsletter_compliance/
    ├── __init__.py
    ├── __manifest__.py
    │
    ├── models/
    │   ├── __init__.py
    │   ├── consent_purpose.py
    │   ├── consent_record.py
    │   ├── suppression_reason.py
    │   ├── suppression_entry.py
    │   └── res_partner.py
    │
    ├── wizard/
    │   ├── __init__.py
    │   ├── withdraw_consent.py
    │   └── reinstate_suppression.py
    │
    ├── security/
    │   ├── newsletter_compliance_groups.xml
    │   ├── ir.model.access.csv
    │   └── newsletter_compliance_rules.xml
    │
    ├── data/
    │   ├── sequences.xml
    │   └── suppression_reason_data.xml
    │
    ├── views/
    │   ├── consent_purpose_views.xml
    │   ├── consent_record_views.xml
    │   ├── suppression_reason_views.xml
    │   ├── suppression_entry_views.xml
    │   ├── res_partner_views.xml
    │   └── menu_views.xml
    │
    └── tests/
        ├── __init__.py
        ├── test_consent.py
        ├── test_suppression.py
        └── test_security.py

This follows Odoo's normal module layout: models in Python, security and view definitions as data files, all referenced from the manifest. ([Odoo](https://www.odoo.com/documentation/19.0/de/developer/tutorials/define_module_data.html?utm_source=chatgpt.com "Define module data — Odoo 19.0 Dokumentation"))

* * *

# 3\. Manifest

    {
        "name": "Newsletter Compliance",
        "summary": "Consent and suppression governance for Odoo Email Marketing",
        "version": "19.0.1.0.0",
        "category": "Marketing/Email Marketing",
        "license": "LGPL-3",
        "author": "Your Organization",
    
        "depends": [
            "base",
            "contacts",
            "mail",
            "mass_mailing",
        ],
    
        "data": [
            "security/newsletter_compliance_groups.xml",
            "security/ir.model.access.csv",
            "security/newsletter_compliance_rules.xml",
    
            "data/sequences.xml",
            "data/suppression_reason_data.xml",
    
            "views/consent_purpose_views.xml",
            "views/consent_record_views.xml",
            "views/suppression_reason_views.xml",
            "views/suppression_entry_views.xml",
            "views/res_partner_views.xml",
            "views/menu_views.xml",
    
            "wizard/withdraw_consent_views.xml",
            "wizard/reinstate_suppression_views.xml",
        ],
    
        "application": False,
        "installable": True,
        "auto_install": False,
    }

* * *

# 4\. Data model

I recommend four R1 models.

    newsletter.consent.purpose
    newsletter.consent.record
    newsletter.suppression.reason
    newsletter.suppression.entry

and extend:

    res.partner

The source explicitly models consent as recipient + purpose/category + timestamp + source + status and suppression as email + reason + timestamp.

* * *

# 5\. Consent Purpose

## Model

    _name = "newsletter.consent.purpose"

Think of this as the **communication purpose**, not merely a mailing list.

Examples:

    Corporate Newsletter
    Healthcare Newsletter
    Product Updates
    Events & Webinars
    Promotional Offers
    Insurance Updates

## Fields

| Technical field | Label | Type | Required |
| --- | --- | --- | --- |
| name | Name | Char | ✅ |
| code | Code | Char | ✅ |
| description | Description | Text |  |
| requires_explicit_consent | Explicit Consent Required | Boolean | ✅ |
| privacy_notice_version | Privacy Notice Version | Char | ✅ |
| retention_days | Retention Days | Integer |  |
| active | Active | Boolean | ✅ |
| company_id | Company | Many2one res.company | ✅ |

For R1, I would **not** introduce legal-basis complexity unless you specifically need it. Your source describes recorded valid consent as the governing basis for marketing/newsletters.

## Python

    from odoo import fields, models
    
    
    class NewsletterConsentPurpose(models.Model):
        _name = "newsletter.consent.purpose"
        _description = "Newsletter Consent Purpose"
        _order = "name"
    
        name = fields.Char(required=True, index=True)
        code = fields.Char(required=True, index=True)
    
        description = fields.Text()
    
        requires_explicit_consent = fields.Boolean(
            string="Explicit Consent Required",
            default=True,
            required=True,
        )
    
        privacy_notice_version = fields.Char(
            string="Privacy Notice Version",
            required=True,
        )
    
        retention_days = fields.Integer(
            default=2555,
            help="Default retention period for consent evidence.",
        )
    
        active = fields.Boolean(default=True)
    
        company_id = fields.Many2one(
            "res.company",
            required=True,
            default=lambda self: self.env.company,
            index=True,
        )
    
        _sql_constraints = [
            (
                "code_company_unique",
                "unique(code, company_id)",
                "Consent purpose code must be unique per company.",
            ),
        ]

I used `2555` only as an illustrative seven-year default. Make the actual value match your approved retention policy; the requirement itself intentionally leaves retention duration to organizational policy.

* * *

# 6\. Consent Record

## Model

    newsletter.consent.record

This becomes the authoritative compliance record.

## Key principle

Do not put:

    marketing_consent = True

on `res.partner` and consider the problem solved.

Instead:

    Recipient
       │
       ├── Corporate Newsletter → Active
       ├── Product Updates       → Withdrawn
       └── Healthcare Updates    → Active

That supports purpose-specific consent.

## Fields

| Field | Type |
| --- | --- |
| reference | Char |
| partner_id | Many2one res.partner |
| email | Char |
| email_normalized | Char |
| purpose_id | Many2one |
| status | Selection |
| given_at | Datetime |
| expires_at | Datetime |
| withdrawn_at | Datetime |
| source | Selection |
| channel | Selection |
| privacy_notice_version | Char |
| source_reference | Char |
| consent_text | Text |
| evidence_attachment_id | Many2one ir.attachment |
| withdrawal_reason | Text |
| withdrawal_source | Selection |
| supersedes_id | Many2one self |
| company_id | Many2one |
| active | Boolean |

* * *

# 7\. Consent states

Use:

    status = fields.Selection([
        ("pending", "Pending"),
        ("active", "Active"),
        ("withdrawn", "Withdrawn"),
        ("expired", "Expired"),
        ("invalidated", "Invalidated"),
        ("superseded", "Superseded"),
    ])

State logic:

    Pending
       ↓
    Active
       ├────────────→ Withdrawn
       ├────────────→ Expired
       ├────────────→ Invalidated
       └────────────→ Superseded

Do not allow:

    Withdrawn → Active

Instead create a **new consent record**.

Example:

    CONS-000012
    Product Updates
    01-Jan-2026
    WITHDRAWN
    
    CONS-000087
    Product Updates
    25-Aug-2026
    ACTIVE
    Supersedes: CONS-000012

This preserves historical evidence.

* * *

# 8\. Consent record implementation

Core skeleton:

    from odoo import api, fields, models, _
    from odoo.exceptions import ValidationError, UserError
    
    
    class NewsletterConsentRecord(models.Model):
        _name = "newsletter.consent.record"
        _description = "Newsletter Consent Record"
        _inherit = ["mail.thread", "mail.activity.mixin"]
        _order = "given_at desc, id desc"
    
        reference = fields.Char(
            readonly=True,
            copy=False,
            default="New",
            tracking=True,
        )
    
        partner_id = fields.Many2one(
            "res.partner",
            required=True,
            index=True,
            ondelete="restrict",
            tracking=True,
        )
    
        email = fields.Char(
            related="partner_id.email",
            readonly=True,
        )
    
        email_normalized = fields.Char(
            required=True,
            index=True,
            readonly=True,
        )
    
        purpose_id = fields.Many2one(
            "newsletter.consent.purpose",
            required=True,
            index=True,
            ondelete="restrict",
            tracking=True,
        )
    
        status = fields.Selection(
            [
                ("pending", "Pending"),
                ("active", "Active"),
                ("withdrawn", "Withdrawn"),
                ("expired", "Expired"),
                ("invalidated", "Invalidated"),
                ("superseded", "Superseded"),
            ],
            default="pending",
            required=True,
            index=True,
            tracking=True,
        )
    
        given_at = fields.Datetime(tracking=True)
        expires_at = fields.Datetime(tracking=True)
    
        withdrawn_at = fields.Datetime(
            readonly=True,
            tracking=True,
        )
    
        source = fields.Selection(
            [
                ("website", "Website"),
                ("email", "Email"),
                ("paper", "Paper"),
                ("phone", "Phone"),
                ("in_person", "In Person"),
                ("crm", "CRM"),
                ("import", "Controlled Import"),
                ("api", "API"),
                ("manual", "Authorized Manual Entry"),
                ("other", "Other"),
            ],
            required=True,
            tracking=True,
        )
    
        channel = fields.Selection(
            [
                ("web", "Web"),
                ("email", "Email"),
                ("phone", "Phone"),
                ("in_person", "In Person"),
                ("paper", "Paper"),
                ("system", "System"),
                ("other", "Other"),
            ],
            required=True,
            tracking=True,
        )
    
        privacy_notice_version = fields.Char(
            required=True,
            tracking=True,
        )
    
        source_reference = fields.Char()
        consent_text = fields.Text()
    
        evidence_attachment_id = fields.Many2one(
            "ir.attachment",
            ondelete="restrict",
        )
    
        withdrawal_reason = fields.Text(readonly=True)
    
        withdrawal_source = fields.Selection(
            [
                ("unsubscribe", "Unsubscribe Link"),
                ("email", "Email Request"),
                ("phone", "Phone Request"),
                ("portal", "Preference Centre"),
                ("manual", "Authorized Manual Action"),
                ("api", "API"),
                ("other", "Other"),
            ],
            readonly=True,
        )
    
        supersedes_id = fields.Many2one(
            "newsletter.consent.record",
            string="Superseded Consent",
            readonly=True,
            ondelete="restrict",
        )
    
        company_id = fields.Many2one(
            "res.company",
            required=True,
            default=lambda self: self.env.company,
            index=True,
        )
    
        active = fields.Boolean(default=True)

* * *

# 9\. Email normalization

Centralize normalization.

For R1:

    @api.model
    def _normalize_email(self, email):
        return (email or "").strip().lower()

When creating a consent:

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            partner = self.env["res.partner"].browse(
                vals.get("partner_id")
            )
    
            vals["email_normalized"] = self._normalize_email(
                partner.email
            )
    
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code(
                        "newsletter.consent.record"
                    )
                    or "New"
                )
    
        return super().create(vals_list)

Later we can replace simplistic normalization with Odoo's own mail utility where appropriate.

* * *

# 10\. Consent integrity rules

Add constraints:

    @api.constrains("status", "given_at")
    def _check_active_consent_timestamp(self):
        for rec in self:
            if rec.status == "active" and not rec.given_at:
                raise ValidationError(
                    _("Active consent must have a consent timestamp.")
                )

and:

    @api.constrains("given_at", "expires_at")
    def _check_expiry_date(self):
        for rec in self:
            if (
                rec.given_at
                and rec.expires_at
                and rec.expires_at <= rec.given_at
            ):
                raise ValidationError(
                    _("Expiry must occur after consent was given.")
                )

* * *

# 11\. Prevent changing finalized evidence

After a consent becomes:

    Active
    Withdrawn
    Expired
    Superseded

fields such as:

    Recipient
    Purpose
    Given At
    Consent Source
    Privacy Notice Version
    Evidence

should not simply be edited.

Override `write()`:

    def write(self, vals):
        protected = {
            "partner_id",
            "email_normalized",
            "purpose_id",
            "given_at",
            "source",
            "channel",
            "privacy_notice_version",
            "consent_text",
            "evidence_attachment_id",
        }
    
        finalized = self.filtered(
            lambda r: r.status in {
                "active",
                "withdrawn",
                "expired",
                "superseded",
            }
        )
    
        if finalized and protected.intersection(vals):
            raise UserError(
                _(
                    "Finalized consent evidence cannot be changed. "
                    "Create a superseding consent record instead."
                )
            )
    
        return super().write(vals)

This implements a crucial audit principle missing from basic Odoo contact fields.

* * *

# 12\. Suppression Reason Master

Rather than hard-coding every reason in a Selection field, make reasons configurable.

Model:

    newsletter.suppression.reason

Fields:

| Field | Purpose |
| --- | --- |
| name | Description |
| code | Machine-readable code |
| category | Bounce / Complaint / Unsubscribe / Compliance |
| default_scope | Global / Brand / Purpose |
| auto_suppress | Automatically create suppression |
| allow_reinstatement | Can it be reversed? |
| active | Active |
| company_id | Company |

* * *

# 13\. Initial suppression reasons

Load these automatically:

| Code | Reason | Default scope |
| --- | --- | --- |
| UNSUBSCRIBE | Unsubscribe | Purpose |
| GLOBAL_OPT_OUT | Global Opt-Out | Global |
| HARD_BOUNCE | Hard Bounce | Global |
| SOFT_BOUNCE_LIMIT | Repeated Soft Bounce | Global |
| COMPLAINT | Spam Complaint | Global |
| INVALID_ADDRESS | Invalid Email Address | Global |
| LEGAL_HOLD | Legal Restriction | Global |
| COMPLIANCE_HOLD | Compliance Hold | Global |
| PURPOSE_OPT_OUT | Purpose-Specific Opt-Out | Purpose |
| MANUAL | Authorized Manual Suppression | Configurable |
| DATA_QUALITY | Data Quality Issue | Global |

These correspond to the document's requirement to distinguish hard bounce, complaint, unsubscribe, and repeated soft-bounce suppression.

* * *

# 14\. Suppression Entry

Model:

    newsletter.suppression.entry

Fields:

| Field | Type |
| --- | --- |
| reference | Char |
| partner_id | Many2one |
| email_normalized | Char |
| scope | Selection |
| purpose_id | Many2one |
| reason_id | Many2one |
| effective_from | Datetime |
| effective_until | Datetime |
| active | Boolean |
| source | Selection |
| details | Text |
| evidence_attachment_id | Many2one |
| reinstated_at | Datetime |
| reinstated_by_id | Many2one |
| reinstatement_reason | Text |
| company_id | Many2one |

For R1 use three scopes:

    GLOBAL
    PURPOSE
    MAILING_LIST

We can add Brand in a later release if multi-brand requirements require an independent model.

* * *

# 15\. Suppression model

    class NewsletterSuppressionEntry(models.Model):
        _name = "newsletter.suppression.entry"
        _description = "Newsletter Suppression Entry"
        _inherit = ["mail.thread", "mail.activity.mixin"]
        _order = "effective_from desc"
    
        reference = fields.Char(
            readonly=True,
            copy=False,
            default="New",
        )
    
        partner_id = fields.Many2one(
            "res.partner",
            required=True,
            ondelete="restrict",
            index=True,
            tracking=True,
        )
    
        email_normalized = fields.Char(
            required=True,
            readonly=True,
            index=True,
        )
    
        scope = fields.Selection(
            [
                ("global", "Global"),
                ("purpose", "Consent Purpose"),
                ("mailing_list", "Mailing List"),
            ],
            required=True,
            default="global",
            tracking=True,
        )
    
        purpose_id = fields.Many2one(
            "newsletter.consent.purpose",
            ondelete="restrict",
        )
    
        mailing_list_id = fields.Many2one(
            "mailing.list",
            ondelete="restrict",
        )
    
        reason_id = fields.Many2one(
            "newsletter.suppression.reason",
            required=True,
            ondelete="restrict",
            tracking=True,
        )
    
        effective_from = fields.Datetime(
            required=True,
            default=fields.Datetime.now,
            tracking=True,
        )
    
        effective_until = fields.Datetime(tracking=True)
    
        active = fields.Boolean(
            default=True,
            tracking=True,
        )
    
        source = fields.Selection(
            [
                ("unsubscribe", "Unsubscribe"),
                ("bounce", "Bounce"),
                ("complaint", "Complaint"),
                ("manual", "Manual"),
                ("api", "API"),
                ("compliance", "Compliance"),
                ("other", "Other"),
            ],
            required=True,
        )
    
        details = fields.Text()
    
        evidence_attachment_id = fields.Many2one(
            "ir.attachment",
            ondelete="restrict",
        )
    
        reinstated_at = fields.Datetime(readonly=True)
    
        reinstated_by_id = fields.Many2one(
            "res.users",
            readonly=True,
        )
    
        reinstatement_reason = fields.Text(readonly=True)
    
        company_id = fields.Many2one(
            "res.company",
            required=True,
            default=lambda self: self.env.company,
            index=True,
        )

* * *

# 16\. Scope validation

Enforce:

    @api.constrains("scope", "purpose_id", "mailing_list_id")
    def _check_scope(self):
        for rec in self:
            if rec.scope == "purpose" and not rec.purpose_id:
                raise ValidationError(
                    _("Consent Purpose is required for purpose suppression.")
                )
    
            if rec.scope == "mailing_list" and not rec.mailing_list_id:
                raise ValidationError(
                    _("Mailing List is required for mailing-list suppression.")
                )

* * *

# 17\. Important suppression rule

Use this precedence:

    GLOBAL
       ↓ strongest
    
    PURPOSE
       ↓
    
    MAILING LIST

Example:

    Recipient: john@example.com
    
    Global suppression?
    NO
    
    Healthcare Purpose suppression?
    NO
    
    Healthcare Newsletter list suppression?
    YES
    
    → Exclude from that list

or:

    Global suppression?
    YES
    
    → Immediately exclude from everything

R3's eligibility engine will implement the actual evaluation.

* * *

# 18\. Extend Contact

Add computed compliance information to:

    res.partner

Fields:

    consent_record_ids
    consent_count
    
    suppression_entry_ids
    suppression_count
    
    active_consent_count
    active_suppression_count
    
    newsletter_compliance_status

Example:

    class ResPartner(models.Model):
        _inherit = "res.partner"
    
        consent_record_ids = fields.One2many(
            "newsletter.consent.record",
            "partner_id",
            string="Consent Records",
        )
    
        consent_count = fields.Integer(
            compute="_compute_newsletter_compliance_counts"
        )
    
        suppression_entry_ids = fields.One2many(
            "newsletter.suppression.entry",
            "partner_id",
        )
    
        suppression_count = fields.Integer(
            compute="_compute_newsletter_compliance_counts"
        )
    
        active_consent_count = fields.Integer(
            compute="_compute_newsletter_compliance_counts"
        )
    
        active_suppression_count = fields.Integer(
            compute="_compute_newsletter_compliance_counts"
        )

* * *

# 19\. Contact UI

Add smart buttons:

    ┌─────────────────────────────────────────────┐
    │ John Smith                                  │
    │ john@example.com                            │
    │                                             │
    │ [ Consents 3 ]      [ Suppressions 1 ]     │
    │                                             │
    │ Newsletter Compliance                      │
    │ ─────────────────────                      │
    │ Active Consents:        2                   │
    │ Active Suppressions:    1                   │
    └─────────────────────────────────────────────┘

Do **not** display:

    Newsletter Eligible = Yes

yet.

Eligibility depends on a campaign purpose and therefore belongs in R3.

* * *

# 20\. Withdrawal wizard

Never let users simply change:

    Active → Withdrawn

from the form.

Create:

    newsletter.withdraw.consent.wizard

Require:

    Withdrawal Date
    Withdrawal Source
    Reason
    Create Suppression? Yes
    Suppression Scope

When confirmed:

    Active Consent
          ↓
    Withdrawal Wizard
          ↓
    Consent.status = withdrawn
    Consent.withdrawn_at = now
          ↓
    Create Suppression Entry
          ↓
    Audit message

This directly implements withdrawal-of-consent behavior required by RC-09.

* * *

# 21\. Reinstatement wizard

A suppression should not have a simple:

    Active ☑

checkbox editable by everybody.

Create:

    newsletter.reinstate.suppression.wizard

Require:

    Suppression
    Reinstatement Reason
    Evidence / Reference

Only:

    Compliance Administrator

can execute it.

On completion:

    active = False
    reinstated_at = now
    reinstated_by_id = user
    reinstatement_reason = reason

Do **not delete the record**.

* * *

# 22\. Roles

For R1 I recommend four groups:

    Newsletter User
    Compliance Reviewer
    Compliance Administrator
    Audit Reviewer

We will introduce Author, Content Approver, Campaign Operator, etc., in R2.

## Newsletter User

Can:

*   view consent status;
    
*   view whether suppression exists;
    
*   create pending consent if permitted;
    
*   not alter finalized consent;
    
*   not reinstate suppression.
    

## Compliance Reviewer

Can:

*   view all consent records;
    
*   review evidence;
    
*   create/validate consent;
    
*   withdraw consent;
    
*   create suppression.
    

## Compliance Administrator

Can:

*   configure consent purposes;
    
*   configure suppression reasons;
    
*   manage all compliance records;
    
*   reinstate suppression.
    

## Audit Reviewer

Can:

*   read all compliance records;
    
*   make no changes.
    

* * *

# 23\. ACL matrix

| Model | User | Reviewer | Admin | Auditor |
| --- | --- | --- | --- | --- |
| Consent Purpose | R | R | CRUD | R |
| Consent Record | RC | CRW | CRUD* | R |
| Suppression Reason | R | R | CRUD | R |
| Suppression Entry | R | CRW | CRUD* | R |

`*` Server-side code still prevents unsafe changes/deletion of historical evidence.

Odoo ACL permissions are additive, so group inheritance needs to be designed carefully rather than trying to "subtract" access in another group. ([Odoo](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html?utm_source=chatgpt.com "Security in Odoo — Odoo 19.0 documentation"))

* * *

# 24\. Group hierarchy

I would use:

    Newsletter User
          ↑
    Compliance Reviewer
          ↑
    Compliance Administrator

Audit Reviewer remains separate:

    Audit Reviewer

because it should be read-only rather than inherit write rights.

* * *

# 25\. Security groups XML

Conceptually:

    <record id="group_newsletter_compliance_user" model="res.groups">
        <field name="name">Newsletter Compliance User</field>
    </record>
    
    <record id="group_newsletter_compliance_reviewer" model="res.groups">
        <field name="name">Newsletter Compliance Reviewer</field>
        <field name="implied_ids"
               eval="[(4, ref('newsletter_compliance.group_newsletter_compliance_user'))]"/>
    </record>
    
    <record id="group_newsletter_compliance_admin" model="res.groups">
        <field name="name">Newsletter Compliance Administrator</field>
        <field name="implied_ids"
               eval="[(4, ref('newsletter_compliance.group_newsletter_compliance_reviewer'))]"/>
    </record>
    
    <record id="group_newsletter_compliance_auditor" model="res.groups">
        <field name="name">Newsletter Compliance Audit Reviewer</field>
    </record>

* * *

# 26\. Multi-company record rules

Consent and suppression data must stay inside authorized companies.

Apply a global company rule:

    <record id="consent_record_company_rule" model="ir.rule">
        <field name="name">Consent Record Company Access</field>
        <field name="model_id"
               ref="model_newsletter_consent_record"/>
        <field name="domain_force">
            [('company_id', 'in', company_ids)]
        </field>
    </record>

Similarly for:

    Consent Purpose
    Suppression Reason
    Suppression Entry

Odoo record rules run after ACL checks and domains can reference the current user's permitted company IDs. ([Odoo](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html?utm_source=chatgpt.com "Security in Odoo — Odoo 19.0 documentation"))

* * *

# 27\. Sequence numbers

Use:

    CONS-000001
    SUP-000001

XML:

    <record id="seq_newsletter_consent" model="ir.sequence">
        <field name="name">Newsletter Consent Record</field>
        <field name="code">newsletter.consent.record</field>
        <field name="prefix">CONS-</field>
        <field name="padding">6</field>
    </record>
    
    <record id="seq_newsletter_suppression" model="ir.sequence">
        <field name="name">Newsletter Suppression Entry</field>
        <field name="code">newsletter.suppression.entry</field>
        <field name="prefix">SUP-</field>
        <field name="padding">6</field>
    </record>

* * *

# 28\. Menu structure

R1:

    Email Marketing
    │
    └── Compliance
        │
        ├── Overview
        │
        ├── Consent
        │   ├── Consent Records
        │   ├── Active Consents
        │   ├── Withdrawn Consents
        │   └── Consent Purposes
        │
        ├── Suppression
        │   ├── Active Suppressions
        │   ├── All Suppressions
        │   └── Suppression Reasons
        │
        └── Configuration
            ├── Consent Purposes
            └── Suppression Reasons

No separate application icon is necessary yet.

Keep it under **Email Marketing → Compliance**.

* * *

# 29\. Consent list view

Suggested columns:

    Reference
    Contact
    Email
    Purpose
    Status
    Given At
    Expires At
    Source
    Privacy Notice
    Company

Filters:

    Active
    Pending
    Withdrawn
    Expired
    
    Expires This Month
    
    Purpose
    
    Company
    
    Source

Group-by:

    Purpose
    Status
    Source
    Company

* * *

# 30\. Consent form

Proposed layout:

    ┌──────────────────────────────────────────────────────┐
    │ CONS-000121                      ACTIVE              │
    │                                                      │
    │ Contact             John Smith                       │
    │ Email               john@example.com                 │
    │ Purpose             Healthcare Newsletter            │
    │                                                      │
    ├─────────────────────────┬────────────────────────────┤
    │ Consent Evidence        │ Lifecycle                  │
    │                         │                            │
    │ Given At                │ Status                     │
    │ Source                  │ Expires At                 │
    │ Channel                 │ Supersedes                 │
    │ Privacy Notice          │ Withdrawn At               │
    │ Source Reference        │                            │
    │ Evidence Attachment     │                            │
    └─────────────────────────┴────────────────────────────┘
    
    [Withdraw Consent]

Chatter underneath.

* * *

# 31\. Suppression list view

Columns:

    Reference
    Email
    Contact
    Scope
    Purpose/List
    Reason
    Effective From
    Effective Until
    Active
    Company

Filters:

    Active
    Global
    Purpose
    Mailing List
    Hard Bounce
    Complaint
    Unsubscribe

* * *

# 32\. Suppression form

    ┌──────────────────────────────────────────────────────┐
    │ SUP-000783                         ACTIVE            │
    │                                                      │
    │ Contact              John Smith                      │
    │ Email                john@example.com                │
    │ Scope                Purpose                         │
    │ Consent Purpose      Product Promotions              │
    │ Reason               Unsubscribe                     │
    │                                                      │
    │ Effective From       28-Aug-2026 12:44              │
    │ Source               Unsubscribe                     │
    │ Evidence                                             │
    │ Details                                              │
    │                                                      │
    │ Reinstated At                                        │
    │ Reinstated By                                        │
    │ Reinstatement Reason                                 │
    └──────────────────────────────────────────────────────┘
    
    [Reinstate]

Only authorized admins see the Reinstate action.

* * *

# 33\. Standard Odoo blacklist synchronization

This needs careful behavior.

### Global suppression

If:

    scope = global

and reason is something like:

    hard bounce
    complaint
    global opt-out

then synchronize with the standard Email Marketing blacklist.

Conceptually:

    Compliance Suppression
             │
             │ Global
             ▼
    Odoo Email Blacklist

### Purpose suppression

Do **not** put it into global Odoo blacklist.

Otherwise someone opting out of:

    Promotions

would inadvertently stop:

    Healthcare Newsletter
    Corporate News
    Event Notices

The custom preflight engine in R3 will evaluate purpose-specific suppression.

* * *

# 34\. Do not delete consent or suppression history

Override `unlink()`.

For finalized consent:

    def unlink(self):
        if self.filtered(
            lambda r: r.status != "pending"
        ):
            raise UserError(
                _("Finalized consent records cannot be deleted.")
            )
    
        return super().unlink()

For suppression:

    def unlink(self):
        raise UserError(
            _(
                "Suppression records are retained as compliance history. "
                "Reinstate the recipient instead."
            )
        )

This also supports the source requirement for a durable audit history.

* * *

# 35\. R1 business rules

Define these explicitly as developer requirements.

| Rule | Description |
| --- | --- |
| BR-R1-01 | Consent must be associated with a communication purpose |
| BR-R1-02 | Active consent must have a consent timestamp |
| BR-R1-03 | Active consent must have a source |
| BR-R1-04 | Active consent must reference a privacy-notice version |
| BR-R1-05 | Finalized consent evidence cannot be edited |
| BR-R1-06 | Withdrawn consent cannot be reactivated |
| BR-R1-07 | Re-consent creates a new record |
| BR-R1-08 | Withdrawal must be auditable |
| BR-R1-09 | Suppression records cannot be deleted |
| BR-R1-10 | Global suppression may synchronize to Odoo blacklist |
| BR-R1-11 | Purpose suppression must not globally blacklist |
| BR-R1-12 | Only Compliance Admin may reinstate suppression |
| BR-R1-13 | Compliance records are company-isolated |
| BR-R1-14 | All lifecycle state changes appear in chatter |
| BR-R1-15 | Every consent and suppression entry has a stable unique reference |

* * *

# 36\. R1 acceptance tests

Before moving to R2, I would require all of these to pass.

### Consent

1.  Create Consent Purpose `Healthcare Newsletter`.
    
2.  Create active consent for John.
    
3.  System requires timestamp.
    
4.  System requires source/channel.
    
5.  System requires Privacy Notice Version.
    
6.  Consent gets unique `CONS-xxxxxx`.
    
7.  Finalized evidence fields cannot be altered.
    
8.  Withdraw consent through wizard.
    
9.  Withdrawal timestamp is captured.
    
10.  Withdrawal reason is retained.
    
11.  Withdrawn consent cannot simply be reactivated.
    
12.  New consent can supersede withdrawn consent.
    

### Suppression

13.  Create purpose suppression.
    
14.  It remains purpose-specific.
    
15.  Create global suppression.
    
16.  It can synchronize with standard blacklist.
    
17.  Suppression gets `SUP-xxxxxx`.
    
18.  Suppression cannot be deleted.
    
19.  Ordinary user cannot reinstate.
    
20.  Compliance Admin can reinstate with mandatory reason.
    
21.  Historical entry remains after reinstatement.
    

### Contact

22.  Contact shows consent-count smart button.
    
23.  Contact shows suppression-count smart button.
    
24.  Smart buttons show only related records.
    

### Security

25.  Ordinary Newsletter User cannot configure purposes.
    
26.  Reviewer can review consent records.
    
27.  Administrator can configure master data.
    
28.  Auditor has read-only access.
    
29.  Users cannot see records from unauthorized companies.
    
30.  Direct RPC/API calls cannot bypass core `write()`/`unlink()` restrictions.
    

That final point matters because Odoo explicitly cautions that simply hiding UI controls is not equivalent to application security. ([Odoo](https://www.odoo.com/documentation/19.0/developer/tutorials/restrict_data_access.html?utm_source=chatgpt.com "Restrict access to data — Odoo 19.0 documentation"))

* * *

# 37\. R1 traceability to your requirements

| Original requirement | R1 capability |
| --- | --- |
| BR-02 Demonstrate consent | Consent Register |
| BR-03 Avoid suppressed recipients | Suppression Register foundation |
| FR-02 Suppression exclusion | Data foundation; enforcement R3 |
| FR-03 Valid consent | Consent model; enforcement R3 |
| FR-19 Hard bounce suppression | Suppression reason/model; automation R5 |
| FR-20 Unsubscribe suppression | Suppression model; integration later |
| FR-21 Repeated soft bounce | Reason/model; threshold logic R5 |
| FR-27 Recipient consent history | Consent/contact history foundation |
| NFR-07 Restricted access | Groups + ACL + record rules |
| NFR-09 Traceability | Stable compliance records + chatter |
| RC-07 Valid consent | Consent Register |
| RC-08 Timestamp/source/purpose | Consent fields |
| RC-09 Consent withdrawal | Withdrawal workflow |
| RC-11 Retention | Retention metadata foundation |

The detailed source requirements for consent and suppression are therefore fully represented in the R1 data model, while enforcement during send intentionally remains for R3.

## Recommended R1 completion boundary

When R1 is finished, you should be able to open any Odoo Contact and answer:

> **“What newsletter purposes has this person consented to, when and how did they consent, what have they withdrawn, and are there any active suppressions against them?”**

You should **not yet** claim that Odoo automatically guarantees that only eligible recipients can be emailed. That guarantee comes in **R3 — Preflight & Eligibility Engine**.

The logical next build increment is **R2 — Campaign Governance**, where we extend Odoo 19 Community's Email Marketing campaign model with Consent Purpose, lifecycle states, Content Review, Compliance Review, approvals, change-invalidates-approval rules, and the groundwork for preflight.