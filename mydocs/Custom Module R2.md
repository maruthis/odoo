Yes. For **R2 — Campaign Governance**, we should now extend Odoo 19 Community’s existing **Email Marketing** model rather than create a separate campaign engine.

The important design choice is this: **do not replace Odoo’s native mailing `state`**. Odoo already uses its own states for draft/queued/sending/done behavior. In R2 we add a separate `compliance_state` and use it to govern whether a mailing is allowed to progress toward sending. Odoo 19’s `mailing.mailing` model is the correct extension point, and the standard form already exposes the mailing body, recipient domain/list, campaign reference, sender data, scheduling, and sending lifecycle. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/mass_mailing/views/mailing_mailing_views.xml?utm_source=chatgpt.com "odoo/addons/mass_mailing/views/mailing_mailing_views.xml at 19.0 · odoo/odoo · GitHub"))

Your original requirements require campaign metadata validation before sending, approval/scheduling behavior, exact newsletter content/version control, personalization, consent/suppression traceability, and simple operation for the Campaign Operator. The original SharePoint/Power Automate implementation can therefore be replaced by equivalent Odoo-native campaign governance.

# R2 — Campaign Governance

## 1\. R2 objective

R2 adds these capabilities on top of R1:

| Capability | R2 |
| --- | --- |
| Extend Odoo Email Marketing mailing | ✅ |
| Campaign Compliance ID | ✅ |
| Consent Purpose association | ✅ |
| Campaign owner | ✅ |
| Business/brand metadata | ✅ |
| Content Review | ✅ |
| Compliance Review | ✅ |
| Approval history | ✅ |
| Separation of duties | ✅ |
| Change invalidates approval | ✅ |
| Required metadata validation | ✅ |
| Campaign status dashboard | ✅ |
| Scheduled-send governance | ✅ Foundation |
| Preflight recipient eligibility | R3 |
| Actual server-side eligibility send blocking | R3 |
| Recipient event ledger | R4 |
| Immutable as-sent archive | R4 |

* * *

# 2\. Important architecture decision

Keep Odoo’s native model:

    mailing.mailing

and extend it:

    class MailingMailing(models.Model):
        _inherit = "mailing.mailing"

Odoo 19’s own code uses `action_put_in_queue()` when scheduling and `action_send_mail()` for sending. Those are natural enforcement points for R3 later. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/marketing_card/models/mailing_mailing.py?utm_source=chatgpt.com "odoo/addons/marketing_card/models/mailing_mailing.py at 19.0 · odoo/odoo · GitHub"))

For R2, however, we primarily introduce governance.

Conceptually:

                      ODOO NATIVE
                   mailing.mailing
                         │
           ┌─────────────┴─────────────┐
           │                           │
     Native Mailing State      Compliance State
           │                           │
     Draft                       Draft
     In Queue                    Content Review
     Sending                     Compliance Review
     Done                        Approved
                                 Preflight Required
                                 Ready to Send
                                 Rejected
                                 Cancelled

This prevents us from interfering with standard Odoo behavior.

* * *

# 3\. R2 module additions

Extend the R1 module:

    newsletter_compliance/
    │
    ├── models/
    │   ├── mailing_mailing.py
    │   ├── campaign_approval.py
    │   └── campaign_brand.py
    │
    ├── wizard/
    │   ├── submit_content_review.py
    │   ├── reject_campaign.py
    │   └── reset_campaign.py
    │
    ├── views/
    │   ├── mailing_mailing_views.xml
    │   ├── campaign_approval_views.xml
    │   └── campaign_brand_views.xml
    │
    ├── data/
    │   └── campaign_sequences.xml
    │
    └── tests/
        ├── test_campaign_governance.py
        ├── test_campaign_approval.py
        └── test_approval_invalidation.py

Update:

    models/__init__.py
    views/menu_views.xml
    security/ir.model.access.csv
    security/newsletter_compliance_groups.xml

* * *

# 4\. Campaign Compliance ID

Every mailing should get a stable compliance identifier.

Example:

    CMP-2026-000001
    CMP-2026-000002

Do not rely solely on the Odoo database ID.

Add:

    compliance_campaign_id = fields.Char(
        string="Campaign Compliance ID",
        readonly=True,
        copy=False,
        index=True,
    )

Generate through `ir.sequence`.

This becomes the identifier used later across:

    Campaign
    Preflight
    Campaign Run
    Recipient Eligibility
    Send Event
    Campaign Archive

* * *

# 5\. Add a Brand / Business Domain master

Your original requirements explicitly anticipate reusable configuration across different domains/brands rather than duplicating the sending logic.

Create:

    newsletter.campaign.brand

Fields:

| Field | Type |
| --- | --- |
| name | Char |
| code | Char |
| company_id | Many2one |
| email_from | Char |
| reply_to | Char |
| physical_address | Text |
| website_url | Char |
| default_consent_purpose_id | Many2one |
| active | Boolean |

Examples:

    Corporate
    Healthcare
    Insurance Brokerage
    Product Platform

This becomes a useful governance abstraction even if all brands are inside one Odoo company.

* * *

# 6\. Extend `mailing.mailing`

Add these fields.

## Campaign identity

| Technical Field | Label |
| --- | --- |
| compliance_campaign_id | Campaign Compliance ID |
| brand_id | Brand / Business Domain |
| consent_purpose_id | Communication Purpose |
| compliance_owner_id | Compliance Owner |
| business_owner_id | Campaign Owner |
| compliance_state | Compliance Status |

## Approval information

| Field | Purpose |
| --- | --- |
| content_review_requested_at | Review requested |
| content_review_requested_by_id | Requesting user |
| content_approved_by_id | Content approver |
| content_approved_at | Approval time |
| compliance_approved_by_id | Compliance approver |
| compliance_approved_at | Approval time |
| rejected_by_id | Rejecting user |
| rejected_at | Rejection time |
| rejection_reason | Reason |
| approval_version | Governance revision number |

## Governance

| Field | Purpose |
| --- | --- |
| approval_content_hash | Snapshot/hash reference |
| approval_subject | Subject at approval |
| approval_email_from | Sender at approval |
| approval_reply_to | Reply-To at approval |
| approval_recipient_domain | Recipient selection snapshot |
| approval_consent_purpose_id | Purpose at approval |
| approvals_valid | Computed result |
| metadata_valid | Computed |
| compliance_warning | Governance warning |
| requires_compliance_review | Configurable |
| preflight_status | Placeholder for R3 |

* * *

# 7\. Compliance state

I recommend:

    compliance_state = fields.Selection([
        ("draft", "Draft"),
        ("content_review", "Content Review"),
        ("compliance_review", "Compliance Review"),
        ("approved", "Approved"),
        ("preflight_required", "Preflight Required"),
        ("ready", "Ready to Send"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ], default="draft", required=True, tracking=True)

R2 ends effectively at:

    APPROVED
       ↓
    PREFLIGHT REQUIRED

R3 moves it to:

    READY TO SEND

after recipient eligibility evaluation.

* * *

# 8\. Campaign governance workflow

Recommended lifecycle:

                            ┌──────────────┐
                            │    DRAFT     │
                            └──────┬───────┘
                                   │
                        Submit for Content Review
                                   │
                                   ▼
                         ┌──────────────────┐
                         │  CONTENT REVIEW  │
                         └─────┬────────┬───┘
                               │        │
                         Approve      Reject
                               │        │
                               ▼        ▼
                   ┌────────────────┐  REJECTED
                   │COMPLIANCE REVIEW│
                   └──────┬─────┬───┘
                          │     │
                     Approve   Reject
                          │     │
                          ▼     ▼
                      APPROVED  REJECTED
                          │
                          ▼
                  PREFLIGHT REQUIRED
                          │
                          │ R3
                          ▼
                     READY TO SEND

If compliance review is not required:

    Content Approved
           ↓
    Approved
           ↓
    Preflight Required

* * *

# 9\. Why two approvals

Keep:

    Content Approval

and:

    Compliance Approval

separate.

Content approval answers:

> Is this the correct newsletter?

Compliance approval answers:

> Are we permitted to use this content, purpose, sender identity, audience definition, and consent basis?

That separation will make audits considerably clearer.

* * *

# 10\. R2 roles

Expand R1's roles to:

| Role | Purpose |
| --- | --- |
| Newsletter Author | Creates/edits mailing |
| Content Approver | Reviews newsletter content |
| Compliance Reviewer | Reviews campaign compliance |
| Campaign Operator | Schedules/sends after approval/preflight |
| Compliance Administrator | Configuration and exception management |
| Audit Reviewer | Read-only evidence review |

Recommended hierarchy:

    Newsletter Compliance User
           │
           ├── Newsletter Author
           ├── Content Approver
           ├── Campaign Operator
           └── Compliance Reviewer
    
    Compliance Administrator
    
    Audit Reviewer

Do not make:

    Content Approver → Compliance Reviewer

an implied hierarchy.

The same individual may deliberately be assigned both groups, but the roles should remain logically independent.

* * *

# 11\. Separation of duties

Recommended default policy:

    Author cannot content-approve own campaign.

and preferably:

    Author cannot compliance-approve own campaign.

Add configuration later if certain organizations permit exceptions.

Server rule:

    if self.create_uid == self.env.user:
        raise UserError(
            _("You cannot approve a campaign that you authored.")
        )

A better implementation uses a dedicated `business_owner_id` or author field rather than relying purely on `create_uid`.

* * *

# 12\. Required campaign metadata

Before the campaign enters Content Review, validate:

    Campaign Compliance ID
    Campaign Name
    Subject
    Brand
    Consent Purpose
    Recipient Source / Segment
    From Address
    Reply-To
    Newsletter Body
    Business Owner

The source requirement specifically calls for validating Campaign ID, Subject Line and Segment before triggering the campaign.

Since Odoo replaces SharePoint, we strengthen that list slightly.

* * *

# 13\. Metadata validation method

Example:

    def _validate_compliance_metadata(self):
        self.ensure_one()
    
        missing = []
    
        checks = {
            "name": _("Campaign Name"),
            "subject": _("Subject"),
            "brand_id": _("Brand"),
            "consent_purpose_id": _("Consent Purpose"),
            "email_from": _("From Address"),
            "body_html": _("Newsletter Content"),
        }
    
        for field_name, label in checks.items():
            if not self[field_name]:
                missing.append(label)
    
        if not self.mailing_domain and not self.contact_list_ids:
            missing.append(_("Recipient Segment / Mailing List"))
    
        if missing:
            raise ValidationError(
                _("The following campaign information is required:\n• %s")
                % "\n• ".join(missing)
            )
    
        return True

Exact recipient-field checks should align with how your Odoo installation selects recipients.

Odoo 19 supports mailing lists as a native recipient mechanism. ([Odoo](https://www.odoo.com/documentation/19.0/applications/marketing/email_marketing/mailing_lists.html?utm_source=chatgpt.com "Mailing lists — Odoo 19.0 documentation"))

* * *

# 14\. Extend mailing model — skeleton

    from odoo import api, fields, models, _
    from odoo.exceptions import UserError, ValidationError
    
    
    class MailingMailing(models.Model):
        _inherit = "mailing.mailing"
    
        compliance_campaign_id = fields.Char(
            string="Campaign Compliance ID",
            readonly=True,
            copy=False,
            index=True,
            tracking=True,
        )
    
        brand_id = fields.Many2one(
            "newsletter.campaign.brand",
            string="Brand / Business Domain",
            ondelete="restrict",
            tracking=True,
        )
    
        consent_purpose_id = fields.Many2one(
            "newsletter.consent.purpose",
            string="Consent Purpose",
            ondelete="restrict",
            tracking=True,
        )
    
        business_owner_id = fields.Many2one(
            "res.users",
            string="Campaign Owner",
            default=lambda self: self.env.user,
            tracking=True,
        )
    
        compliance_owner_id = fields.Many2one(
            "res.users",
            string="Compliance Owner",
            tracking=True,
        )
    
        compliance_state = fields.Selection(
            [
                ("draft", "Draft"),
                ("content_review", "Content Review"),
                ("compliance_review", "Compliance Review"),
                ("approved", "Approved"),
                ("preflight_required", "Preflight Required"),
                ("ready", "Ready to Send"),
                ("rejected", "Rejected"),
                ("cancelled", "Cancelled"),
            ],
            default="draft",
            required=True,
            tracking=True,
            copy=False,
        )
    
        content_review_requested_at = fields.Datetime(
            readonly=True,
            copy=False,
        )
    
        content_review_requested_by_id = fields.Many2one(
            "res.users",
            readonly=True,
            copy=False,
        )
    
        content_approved_by_id = fields.Many2one(
            "res.users",
            readonly=True,
            copy=False,
        )
    
        content_approved_at = fields.Datetime(
            readonly=True,
            copy=False,
        )
    
        compliance_approved_by_id = fields.Many2one(
            "res.users",
            readonly=True,
            copy=False,
        )
    
        compliance_approved_at = fields.Datetime(
            readonly=True,
            copy=False,
        )
    
        approval_version = fields.Integer(
            default=0,
            readonly=True,
            copy=False,
        )
    
        approvals_valid = fields.Boolean(
            compute="_compute_approvals_valid"
        )
    
        preflight_status = fields.Selection(
            [
                ("not_run", "Not Run"),
                ("required", "Required"),
                ("passed", "Passed"),
                ("failed", "Failed"),
            ],
            default="not_run",
            copy=False,
        )

* * *

# 15\. Campaign ID generation

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
    
        for record in records:
            if (
                record.mailing_type == "mail"
                and not record.compliance_campaign_id
            ):
                record.compliance_campaign_id = (
                    self.env["ir.sequence"].next_by_code(
                        "newsletter.compliance.campaign"
                    )
                )
    
        return records

Sequence:

    <record id="seq_newsletter_compliance_campaign"
            model="ir.sequence">
        <field name="name">
            Newsletter Compliance Campaign
        </field>
        <field name="code">
            newsletter.compliance.campaign
        </field>
        <field name="prefix">
            CMP-%(year)s-
        </field>
        <field name="padding">6</field>
    </record>

Produces:

    CMP-2026-000001

* * *

# 16\. Submit for content review

Button:

    Submit for Review

Method:

    def action_submit_content_review(self):
        for mailing in self:
            if mailing.compliance_state not in (
                "draft",
                "rejected",
            ):
                raise UserError(
                    _("This campaign cannot be submitted for review.")
                )
    
            mailing._validate_compliance_metadata()
    
            mailing.write({
                "compliance_state": "content_review",
                "content_review_requested_at":
                    fields.Datetime.now(),
                "content_review_requested_by_id":
                    self.env.user.id,
            })
    
            mailing.message_post(
                body=_(
                    "Campaign submitted for content review by %s."
                ) % self.env.user.display_name
            )
    
        return True

* * *

# 17\. Content approval

Button:

    Approve Content

Visible only to Content Approvers.

Method:

    def action_approve_content(self):
        self.ensure_one()
    
        if self.compliance_state != "content_review":
            raise UserError(
                _("Campaign is not awaiting content review.")
            )
    
        if self.business_owner_id == self.env.user:
            raise UserError(
                _("Campaign owners cannot approve their own content.")
            )
    
        self._validate_compliance_metadata()
    
        self.write({
            "content_approved_by_id": self.env.user.id,
            "content_approved_at": fields.Datetime.now(),
            "approval_version": self.approval_version + 1,
            "compliance_state": "compliance_review",
        })
    
        self._capture_content_approval_snapshot()
    
        return True

* * *

# 18\. Content snapshot at approval

At approval, capture the fields that matter.

At minimum:

    Subject
    From
    Reply-To
    HTML
    Recipient Selection
    Consent Purpose
    Brand

Fields:

    approval_subject = fields.Char(readonly=True)
    approval_email_from = fields.Char(readonly=True)
    approval_body_hash = fields.Char(readonly=True)
    approval_recipient_definition = fields.Text(readonly=True)
    approval_consent_purpose_id = fields.Many2one(
        "newsletter.consent.purpose",
        readonly=True,
    )

The snapshot lets us detect changes after approval.

* * *

# 19\. Approval hash

Calculate a SHA-256 over controlled campaign inputs.

For example:

    import hashlib
    import json
    
    
    def _build_approval_hash(self):
        self.ensure_one()
    
        payload = {
            "subject": self.subject or "",
            "email_from": self.email_from or "",
            "reply_to": self.reply_to or "",
            "body_html": self.body_html or "",
            "brand_id": self.brand_id.id or False,
            "consent_purpose_id":
                self.consent_purpose_id.id or False,
            "mailing_domain":
                self.mailing_domain or "",
            "contact_list_ids":
                sorted(self.contact_list_ids.ids),
        }
    
        encoded = json.dumps(
            payload,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    
        return hashlib.sha256(encoded).hexdigest()

Store:

    approval_content_hash

* * *

# 20\. Change invalidates approval

This is one of the most important R2 controls.

Suppose a campaign gets approved:

    Subject:
    "August Healthcare Newsletter"

Then the author changes it to:

    "URGENT — BUY NOW!!!"

The original approval must no longer be valid.

Protected fields:

    subject
    body_html
    body_arch
    email_from
    reply_to
    brand_id
    consent_purpose_id
    mailing_domain
    contact_list_ids

If any of these change after approval:

    Approval → INVALIDATED

and the campaign returns to:

    Draft

or preferably:

    Content Review Required

* * *

# 21\. Implement invalidation

Example:

    GOVERNED_FIELDS = {
        "subject",
        "body_html",
        "body_arch",
        "email_from",
        "reply_to",
        "brand_id",
        "consent_purpose_id",
        "mailing_domain",
        "contact_list_ids",
    }
    
    
    def write(self, vals):
        governed_change = bool(
            self.GOVERNED_FIELDS.intersection(vals)
        )
    
        approved_records = self.filtered(
            lambda r: r.compliance_state in {
                "compliance_review",
                "approved",
                "preflight_required",
                "ready",
            }
        )
    
        result = super().write(vals)
    
        if governed_change:
            approved_records._invalidate_compliance_approval()
    
        return result

Be careful to avoid recursion.

Prefer a dedicated internal context flag:

    with_context(
        skip_compliance_invalidation=True
    )

for internal controlled changes.

* * *

# 22\. Invalidation behavior

    def _invalidate_compliance_approval(self):
        for mailing in self:
            mailing.with_context(
                skip_compliance_invalidation=True
            ).write({
                "compliance_state": "draft",
                "content_approved_by_id": False,
                "content_approved_at": False,
                "compliance_approved_by_id": False,
                "compliance_approved_at": False,
                "preflight_status": "not_run",
            })
    
            mailing.message_post(
                body=_(
                    "Campaign approval was invalidated because "
                    "controlled campaign content or metadata changed."
                )
            )

This event should always be visible in chatter.

* * *

# 23\. Compliance approval

Only users in:

    Newsletter Compliance Reviewer

can execute.

Validation:

    Content approved?
    Consent purpose defined?
    Brand defined?
    Sender valid?
    Recipient segment defined?
    Content unchanged since content approval?

Then:

    def action_approve_compliance(self):
        self.ensure_one()
    
        if self.compliance_state != "compliance_review":
            raise UserError(
                _("Campaign is not awaiting compliance review.")
            )
    
        if not self.content_approved_by_id:
            raise UserError(
                _("Content approval is required first.")
            )
    
        if self.business_owner_id == self.env.user:
            raise UserError(
                _("Campaign owner cannot compliance-approve this campaign.")
            )
    
        self._validate_compliance_metadata()
        self._verify_content_approval_integrity()
    
        self.write({
            "compliance_approved_by_id": self.env.user.id,
            "compliance_approved_at": fields.Datetime.now(),
            "compliance_state": "preflight_required",
            "preflight_status": "required",
        })
    
        return True

We deliberately go to:

    PRE-FLIGHT REQUIRED

rather than Ready to Send.

R3 earns that state.

* * *

# 24\. Reject campaign

Both approvers need a:

    Reject

button.

Do not just set state.

Require a wizard with:

    Reason
    Reviewer Comments
    Return To

Return-to options:

    Draft
    Content Review

Record:

    Rejected By
    Rejected At
    Reason

and chatter message.

* * *

# 25\. Approval history model

I recommend creating:

    newsletter.campaign.approval

instead of relying only on fields in `mailing.mailing`.

Why?

Because a campaign may go through:

    Approval V1
    Content Changed
    Approval V2
    Recipient Segment Changed
    Approval V3

You want to preserve all three.

Fields:

| Field | Purpose |
| --- | --- |
| mailing_id | Campaign |
| approval_version | Version |
| approval_type | Content / Compliance |
| decision | Approved / Rejected / Invalidated |
| reviewer_id | Reviewer |
| reviewed_at | Time |
| comments | Comments |
| content_hash | Approved configuration hash |
| subject_snapshot | Subject |
| recipient_snapshot | Segment |
| consent_purpose_id | Consent basis |
| brand_id | Brand |
| company_id | Company |

This creates a far better audit trail.

* * *

# 26\. Approval record example

    Campaign: CMP-2026-000128
    
    Version 1
    Content Approval
    Approved by: Jane
    28-Aug-2026 10:15
    Hash: 7b4...
    
    Version 1
    Compliance Approval
    Approved by: Sarah
    28-Aug-2026 10:42
    Hash: 7b4...
    
    Version 1
    INVALIDATED
    28-Aug-2026 11:03
    Reason: Subject modified
    
    Version 2
    Content Approval
    Approved by: Jane
    28-Aug-2026 11:15
    
    Version 2
    Compliance Approval
    Approved by: Sarah
    28-Aug-2026 11:30

That is the behavior we want.

* * *

# 27\. Campaign form UI

Extend the native Email Marketing form.

At the top:

    ┌─────────────────────────────────────────────────────────┐
    │ August Healthcare Newsletter                            │
    │ CMP-2026-000128                                         │
    │                                                         │
    │ DRAFT → CONTENT REVIEW → COMPLIANCE REVIEW → PREFLIGHT  │
    └─────────────────────────────────────────────────────────┘

Add compliance status as a status bar.

* * *

# 28\. Governance section

Add a new notebook tab:

    Compliance

Suggested layout:

    ┌──────────────────────┬───────────────────────────┐
    │ Campaign Governance  │ Approval                  │
    ├──────────────────────┼───────────────────────────┤
    │ Campaign ID          │ Content Approved By       │
    │ Brand                │ Content Approved At       │
    │ Consent Purpose      │ Compliance Approved By    │
    │ Campaign Owner       │ Compliance Approved At    │
    │ Compliance Owner     │ Approval Version          │
    │ Compliance Status    │ Approvals Valid           │
    │ Preflight Status     │                           │
    └──────────────────────┴───────────────────────────┘

* * *

# 29\. Buttons

Depending on state:

### Draft

    [Submit for Content Review]

### Content Review

    [Approve Content] [Reject]

### Compliance Review

    [Approve Compliance] [Reject]

### Preflight Required

    [Run Compliance Preflight]

The last button exists only as a placeholder until R3.

Do **not** activate sending yet from the compliance workflow.

* * *

# 30\. Standard send/schedule buttons

This requires care.

Odoo's standard form contains its own actions for sending/scheduling. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/mass_mailing/views/mailing_mailing_views.xml?utm_source=chatgpt.com "odoo/addons/mass_mailing/views/mailing_mailing_views.xml at 19.0 · odoo/odoo · GitHub"))

For R2, modify their visibility so ordinary Campaign Operators only see them when:

    compliance_state = ready

However, UI hiding is not security.

In R3 we will also override:

    action_put_in_queue()
    action_send_mail()

to enforce readiness server-side.

Odoo itself uses these methods as send/schedule paths, so this gives us a reliable hook. ([GitHub](https://github.com/odoo/odoo/blob/19.0/addons/marketing_card/models/mailing_mailing.py?utm_source=chatgpt.com "odoo/addons/marketing_card/models/mailing_mailing.py at 19.0 · odoo/odoo · GitHub"))

* * *

# 31\. Why defer hard send-blocking to R3

Because "approved" is not sufficient.

A campaign can be approved but still contain:

    10,000 recipients
    620 without consent
    100 globally suppressed
    60 purpose-suppressed

So:

    Approved ≠ Ready to Send

Instead:

    Approved
       ↓
    Preflight Required
       ↓
    Eligibility Engine
       ↓
    Ready to Send

That is central to the architecture.

* * *

# 32\. Security groups

Add:

    group_newsletter_author
    group_newsletter_content_approver
    group_newsletter_campaign_operator

Reuse:

    group_newsletter_compliance_reviewer
    group_newsletter_compliance_admin
    group_newsletter_compliance_auditor

* * *

# 33\. R2 access matrix

| Capability | Author | Content Approver | Compliance Reviewer | Operator | Admin | Auditor |
| --- | --- | --- | --- | --- | --- | --- |
| Create mailing | ✅ |  |  |  | ✅ |  |
| Edit draft | ✅ |  |  |  | ✅ |  |
| Submit review | ✅ |  |  |  | ✅ |  |
| Approve content |  | ✅ |  |  | ✅ |  |
| Approve compliance |  |  | ✅ |  | ✅ |  |
| Reject |  | ✅ | ✅ |  | ✅ |  |
| View approvals | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Schedule/send |  |  |  | R3 | ✅* |  |
| Configure brand |  |  |  |  | ✅ |  |
| Configure consent purposes |  |  |  |  | ✅ |  |
| Read audit history | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Modify approval history |  |  |  |  | No normal UI |  |

`*` Even an admin should not casually bypass compliance checks. Administrator technical privilege and compliance approval authority should ideally remain conceptually separate.

* * *

# 34\. Campaign views

Create filters:

    My Campaigns
    Draft
    Awaiting Content Review
    Awaiting Compliance Review
    Preflight Required
    Ready to Send
    Rejected

Group by:

    Compliance State
    Brand
    Consent Purpose
    Campaign Owner
    Compliance Owner

* * *

# 35\. Review queues

Create menu entries:

    Email Marketing
    └── Compliance
        └── Campaign Governance
            ├── My Campaigns
            ├── Content Review Queue
            ├── Compliance Review Queue
            ├── Preflight Required
            ├── Ready to Send
            ├── Rejected
            └── Approval History

This gives each role an operational queue.

* * *

# 36\. Content Review queue

Domain:

    [
        ("compliance_state", "=", "content_review")
    ]

Compliance Review:

    [
        ("compliance_state", "=", "compliance_review")
    ]

Preflight Required:

    [
        ("compliance_state", "=", "preflight_required")
    ]

* * *

# 37\. Brand defaults

When a user selects:

    Healthcare

automatically populate:

    From
    Reply-To
    Consent Purpose
    Physical Address

Example:

    @api.onchange("brand_id")
    def _onchange_brand_id(self):
        if self.brand_id:
            self.email_from = self.brand_id.email_from
    
            if self.brand_id.default_consent_purpose_id:
                self.consent_purpose_id = (
                    self.brand_id.default_consent_purpose_id
                )

Do not overwrite manually configured fields without warning if already populated.

* * *

# 38\. Physical mailing address

Your source requires a valid physical mailing address in every commercial/marketing email. This should therefore become part of campaign governance, not merely template convention.

Add:

    physical_address

either on Brand or Campaign.

Validation:

    No physical address
          ↓
    Cannot submit for Content Review

The source includes this as a regulatory requirement.

* * *

# 39\. Unsubscribe validation

R2 can initially have:

    unsubscribe_confirmed

but I do **not** recommend trusting a checkbox long-term.

Eventually we should validate rendered content or rely on Odoo's standard unsubscribe machinery.

The original requirement expects a functioning unsubscribe mechanism, not merely a statement that one exists.

Actual technical enforcement can be strengthened in R3/R5.

* * *

# 40\. Campaign versioning

Add:

    governance_version

starting at:

    1

When a governed field changes after approval:

    governance_version += 1

Example:

    CMP-2026-000128
    
    Campaign itself stays the same.
    
    Governance Version:
    1 → 2 → 3

This is different from Odoo database versioning and later supports audit reconstruction.

* * *

# 41\. Draft copy behavior

Odoo users may duplicate mailings.

When copied:

    Campaign ID         → generate new
    Compliance state    → Draft
    Approval fields     → empty
    Preflight status    → Not Run
    Approval history    → do not copy

Override `copy_data()` or ensure fields have:

    copy=False

This is important.

A copied campaign must never inherit approval.

* * *

# 42\. Campaign cancellation

Add:

    Cancel Campaign

Allowed when:

    Draft
    Content Review
    Compliance Review
    Approved
    Preflight Required

Record:

    Cancelled By
    Cancelled At
    Cancellation Reason

Do not delete.

* * *

# 43\. Campaign reset

Use a controlled:

    Return to Draft

wizard.

Reasons:

    Content correction
    Recipient segment change
    Consent purpose correction
    Sender correction
    Campaign postponed
    Other

Resetting should invalidate existing approvals.

* * *

# 44\. Chatter

Because `mailing.mailing` uses Odoo mail capabilities, use chatter for human-readable governance events.

Record:

    Campaign submitted for content review
    Content approved by X
    Compliance approved by Y
    Approval invalidated because subject changed
    Campaign rejected by Y
    Campaign returned to Draft
    Campaign cancelled

Do not rely on chatter alone for structured audit history; that's why we also created `newsletter.campaign.approval`.

* * *

# 45\. Business rules

Define these as R2 formal requirements.

| Rule | Requirement |
| --- | --- |
| R2-BR-01 | Every governed mailing has a unique Campaign Compliance ID |
| R2-BR-02 | Every campaign must have a Consent Purpose |
| R2-BR-03 | Every campaign must have a recipient definition |
| R2-BR-04 | Required metadata must exist before review |
| R2-BR-05 | Content approval precedes compliance approval |
| R2-BR-06 | Campaign owner cannot approve own campaign |
| R2-BR-07 | Controlled content changes invalidate approval |
| R2-BR-08 | Approval history cannot be deleted through normal UI |
| R2-BR-09 | Rejected campaigns require a reason |
| R2-BR-10 | Copied campaigns do not inherit approval |
| R2-BR-11 | Approved campaign becomes Preflight Required |
| R2-BR-12 | Approved does not mean Ready to Send |
| R2-BR-13 | Cancelled campaigns remain retained |
| R2-BR-14 | Campaign governance honors multi-company access |
| R2-BR-15 | All governance state transitions are logged |

* * *

# 46\. Acceptance tests

R2 should not be considered finished until these pass.

### Creation

1.  Create Email Marketing mailing.
    
2.  Campaign Compliance ID generated automatically.
    
3.  Compliance status defaults to Draft.
    
4.  Campaign owner defaults correctly.
    

### Metadata

5.  Submit without Subject → blocked.
    
6.  Submit without Consent Purpose → blocked.
    
7.  Submit without Brand → blocked.
    
8.  Submit without recipients → blocked.
    
9.  Submit without newsletter content → blocked.
    
10.  Valid campaign → Content Review.
    

### Content review

11.  Author cannot approve own campaign.
    
12.  Unauthorized user cannot approve.
    
13.  Content Approver can approve.
    
14.  Approval record generated.
    
15.  Campaign advances to Compliance Review.
    

### Compliance review

16.  Compliance Reviewer can approve.
    
17.  Unauthorized user cannot approve.
    
18.  Compliance approval record generated.
    
19.  Campaign moves to Preflight Required.
    

### Change handling

20.  Change Subject after approval → approvals invalidated.
    
21.  Change HTML → approvals invalidated.
    
22.  Change Consent Purpose → approvals invalidated.
    
23.  Change recipients → approvals invalidated.
    
24.  Change From address → approvals invalidated.
    
25.  Chatter records invalidation.
    
26.  Approval history retains previous decision.
    

### Copy

27.  Duplicate campaign.
    
28.  New Campaign ID generated.
    
29.  Compliance state = Draft.
    
30.  No approver copied.
    
31.  No approval history copied.
    

### Rejection

32.  Reviewer rejects campaign.
    
33.  Reason mandatory.
    
34.  Rejecting user/timestamp stored.
    
35.  Campaign can be returned to Draft.
    

### Security

36.  Author cannot alter approval records.
    
37.  Auditor cannot modify campaigns.
    
38.  Multi-company record isolation works.
    
39.  Direct RPC action cannot execute approval without required group.
    
40.  No R2 action can place a campaign into Ready to Send without R3.
    

* * *

# 47\. Requirement traceability

R2 translates the original technology-specific workflow into Odoo-native equivalents:

| Original Requirement | Odoo R2 Equivalent |
| --- | --- |
| FR-05 campaign metadata | Mailing + governance metadata |
| FR-06 approved/scheduled trigger | Compliance workflow |
| FR-07 metadata validation | _validate_compliance_metadata() |
| FR-08 initiation endpoint | No longer needed |
| FR-09 retrieve approved content | Content stored directly in mailing |
| FR-10 exact approved version | Governance version + approval hash |
| FR-11 personalization | Standard Odoo Email Marketing |
| FR-12 unsubscribe | Standard Odoo + later validation |
| NFR-09 newsletter version traceability | Approval history + hashes |
| NFR-11 simple operator flow | Review → Approve → Preflight → Send |

The original FR-05–FR-12 wording assumes SharePoint/Power Automate, but the business intent is content governance, metadata completeness, approved content selection, personalization and unsubscribe functionality.

* * *

# 48\. End state after R2

At the completion of R2, a Campaign Operator should see something like:

    Healthcare Monthly Newsletter
    CMP-2026-000128
    
    Brand:
    Healthcare
    
    Consent Purpose:
    Healthcare Newsletter
    
    Campaign Owner:
    Ravi Kumar
    
    Recipients:
    Healthcare Subscribers – India
    
    Subject:
    August Healthcare Insights
    
    Content Approval:
    ✓ Approved by Jane Smith
    28-Aug-2026 14:10
    
    Compliance Approval:
    ✓ Approved by Sarah Jones
    28-Aug-2026 14:23
    
    Compliance Status:
    PRE-FLIGHT REQUIRED
    
    Recipients Targeted:
    Not yet evaluated
    
    [ Run Compliance Preflight ]

And critically:

    SEND

is **not yet authorized**.

That becomes the responsibility of **R3 — Preflight & Recipient Eligibility**, where we connect the R1 Consent/Suppression foundation to the R2 Campaign Governance model and determine, recipient by recipient, who can actually receive the newsletter.