import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NewsletterRecipientEligibility(models.Model):
    _name = "newsletter.recipient.eligibility"
    _inherit = ["newsletter.retention.mixin"]
    _description = "Newsletter Recipient Eligibility Decision"
    _order = "campaign_run_id, evaluation_sequence"

    campaign_run_id = fields.Many2one(
        "newsletter.campaign.run",
        required=True,
        index=True,
        ondelete="cascade",
    )

    mailing_id = fields.Many2one(
        "mailing.mailing",
        required=True,
        index=True,
        ondelete="cascade",
    )

    partner_id = fields.Many2one("res.partner", ondelete="set null")
    mailing_contact_id = fields.Many2one("mailing.contact", ondelete="set null")

    recipient_model = fields.Char()
    recipient_res_id = fields.Integer()

    email_original = fields.Char()
    email_normalized = fields.Char(index=True)

    status = fields.Selection(
        [
            ("eligible", "Eligible"),
            ("excluded", "Excluded"),
        ],
        required=True,
        index=True,
    )

    reason_code = fields.Selection(
        [
            ("eligible", "Eligible"),
            ("missing_email", "Missing Email"),
            ("invalid_email", "Invalid Email"),
            ("duplicate_email", "Duplicate Email"),
            ("missing_consent", "Missing Consent"),
            ("pending_consent", "Pending Consent"),
            ("withdrawn_consent", "Withdrawn Consent"),
            ("expired_consent", "Expired Consent"),
            ("invalidated_consent", "Invalidated Consent"),
            ("wrong_consent_purpose", "Wrong Consent Purpose"),
            ("global_blacklist", "Global Blacklist"),
            ("global_suppression", "Global Suppression"),
            ("brand_suppression", "Brand Suppression"),
            ("purpose_suppression", "Purpose Suppression"),
            ("mailing_list_suppression", "Mailing List Suppression"),
            ("campaign_suppression", "Campaign Suppression"),
            ("mailing_list_opt_out", "Mailing List Opt-Out"),
            ("already_sent", "Already Sent"),
            ("company_mismatch", "Company Mismatch"),
            ("manual_hold", "Manual Hold"),
            ("other", "Other"),
        ],
        required=True,
        index=True,
    )

    reason_detail = fields.Text()

    consent_record_id = fields.Many2one("newsletter.consent.record", ondelete="set null")
    suppression_entry_id = fields.Many2one("newsletter.suppression.entry", ondelete="set null")
    mailing_list_id = fields.Many2one("mailing.list", ondelete="set null")

    duplicate_of_id = fields.Many2one(
        "newsletter.recipient.eligibility", ondelete="set null", readonly=True
    )

    evaluated_at = fields.Datetime()
    ruleset_version = fields.Char()
    evaluation_sequence = fields.Integer()
    decision_hash = fields.Char(readonly=True)

    dispatch_state = fields.Selection(
        [
            ("not_queued", "Not Queued"),
            ("queued", "Queued"),
            ("processing", "Processing"),
            ("sent", "Sent"),
            ("retry_pending", "Retry Pending"),
            ("failed", "Failed"),
            ("blocked", "Blocked at Dispatch"),
            ("cancelled", "Cancelled"),
        ],
        default="not_queued",
    )

    delivery_state = fields.Selection(
        [
            ("unknown", "Unknown"),
            ("accepted", "Accepted"),
            ("delivered", "Delivered"),
            ("delayed", "Delayed"),
            ("soft_bounce", "Soft Bounce"),
            ("hard_bounce", "Hard Bounce"),
            ("complaint", "Complaint"),
        ],
        default="unknown",
    )

    dispatch_attempt_count = fields.Integer(default=0)
    first_queued_at = fields.Datetime()
    last_queued_at = fields.Datetime()
    first_sent_at = fields.Datetime()
    last_attempt_at = fields.Datetime()
    next_retry_at = fields.Datetime()

    provider_message_id = fields.Char()
    last_error_code = fields.Char()
    last_error_message = fields.Text()
    last_error_retryable = fields.Boolean(default=False)

    dispatch_lock_token = fields.Char()
    dispatch_locked_at = fields.Datetime()

    frozen = fields.Boolean(default=False, readonly=True)

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    event_ids = fields.One2many(
        "newsletter.send.event", "eligibility_id", string="Send Events"
    )

    # Fields that legitimately change after the record is frozen, as part
    # of R4 execution - everything else stays locked once frozen.
    EXECUTION_MUTABLE_FIELDS = {
        "dispatch_state",
        "delivery_state",
        "dispatch_attempt_count",
        "first_queued_at",
        "last_queued_at",
        "first_sent_at",
        "last_attempt_at",
        "next_retry_at",
        "provider_message_id",
        "last_error_code",
        "last_error_message",
        "last_error_retryable",
        "dispatch_lock_token",
        "dispatch_locked_at",
    }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._compute_decision_hash()
        return records

    def _compute_decision_hash(self):
        for record in self:
            payload = "|".join(
                [
                    record.email_normalized or "",
                    record.status or "",
                    record.reason_code or "",
                    str(record.consent_record_id.id or ""),
                    str(record.suppression_entry_id.id or ""),
                ]
            )
            record.with_context(skip_eligibility_freeze_guard=True).write(
                {"decision_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest()}
            )

    def write(self, vals):
        if not self.env.context.get("skip_eligibility_freeze_guard"):
            frozen = self.filtered("frozen")
            if frozen and set(vals) - self.EXECUTION_MUTABLE_FIELDS:
                raise UserError(
                    _(
                        "Frozen eligibility decisions cannot be edited. "
                        "Fix the underlying consent/suppression/email data "
                        "and run preflight again instead."
                    )
                )
        return super().write(vals)

    def pseudonymize(self):
        """R6 section 27: replace direct identity (partner_id, email) with
        nothing while retaining campaign/event linkage, timestamps, and
        outcome - so aggregate reporting stays correct after the
        individual's identity is gone.
        """
        for record in self:
            if record.retention_state == "pseudonymized":
                continue
            record.with_context(skip_eligibility_freeze_guard=True).write(
                {
                    "partner_id": False,
                    "mailing_contact_id": False,
                    "email_original": False,
                    "email_normalized": False,
                    "retention_state": "pseudonymized",
                }
            )

    def unlink(self):
        raise UserError(
            _(
                "Eligibility decisions are retained as compliance history "
                "and cannot be deleted."
            )
        )
