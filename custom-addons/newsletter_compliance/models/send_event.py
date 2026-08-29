import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError

EVENT_TYPES = [
    ("recipient_targeted", "Recipient Targeted"),
    ("eligibility_passed", "Eligibility Passed"),
    ("eligibility_excluded", "Eligibility Excluded"),
    ("queued", "Queued"),
    ("dispatch_started", "Dispatch Started"),
    ("dispatch_recheck_passed", "Dispatch Recheck Passed"),
    ("dispatch_recheck_blocked", "Dispatch Recheck Blocked"),
    ("send_attempted", "Send Attempted"),
    ("send_accepted", "Send Accepted"),
    ("send_failed", "Send Failed"),
    ("retry_scheduled", "Retry Scheduled"),
    ("retry_started", "Retry Started"),
    ("send_failed_final", "Send Failed (Final)"),
    ("accepted", "Accepted"),
    ("delivered", "Delivered"),
    ("delayed", "Delayed"),
    ("delivery_delayed", "Delivery Delayed"),
    ("soft_bounce", "Soft Bounce"),
    ("hard_bounce", "Hard Bounce"),
    ("complaint", "Complaint"),
    ("unsubscribed", "Unsubscribed"),
    ("unsubscribe", "Unsubscribe"),
    ("provider_rejected", "Provider Rejected"),
    ("provider_dropped", "Provider Dropped"),
    ("unknown", "Unknown"),
    ("suppression_created", "Suppression Created"),
    ("campaign_cancelled", "Campaign Cancelled"),
    ("campaign_completed", "Campaign Completed"),
]


class NewsletterSendEvent(models.Model):
    _name = "newsletter.send.event"
    _description = "Newsletter Send Event"
    _inherit = ["newsletter.retention.mixin"]
    _order = "id"
    _rec_name = "reference"

    reference = fields.Char(readonly=True, copy=False, default="New")

    campaign_run_id = fields.Many2one(
        "newsletter.campaign.run", required=True, index=True, ondelete="cascade"
    )
    mailing_id = fields.Many2one(
        "mailing.mailing", required=True, index=True, ondelete="cascade"
    )
    eligibility_id = fields.Many2one(
        "newsletter.recipient.eligibility", index=True, ondelete="cascade"
    )
    partner_id = fields.Many2one("res.partner", ondelete="set null")
    mailing_contact_id = fields.Many2one("mailing.contact", ondelete="set null")
    email_normalized = fields.Char(index=True)

    event_type = fields.Selection(EVENT_TYPES, required=True, index=True)

    event_timestamp = fields.Datetime(required=True, default=fields.Datetime.now)
    processing_timestamp = fields.Datetime(required=True, default=fields.Datetime.now)

    attempt_number = fields.Integer(default=0)

    provider_message_id = fields.Char()
    provider_event_id = fields.Char(index=True)
    correlation_id = fields.Char(index=True)

    error_code = fields.Char()
    error_message = fields.Text()

    source = fields.Selection(
        [
            ("odoo", "Odoo"),
            ("provider", "Provider"),
            ("user", "User"),
        ],
        default="odoo",
        required=True,
    )

    raw_payload = fields.Text()

    payload_hash = fields.Char(readonly=True)
    previous_event_hash = fields.Char(readonly=True)
    event_hash = fields.Char(readonly=True)

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _provider_event_unique = models.Constraint(
        "unique(source, provider_event_id)",
        "This provider event has already been recorded (idempotency guard).",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("newsletter.send.event") or "New"
                )
        records = super().create(vals_list)
        records._compute_event_hash()
        return records

    def _compute_event_hash(self):
        for event in self:
            previous = self.search(
                [
                    ("campaign_run_id", "=", event.campaign_run_id.id),
                    ("id", "!=", event.id),
                    ("id", "<", event.id),
                ],
                order="id desc",
                limit=1,
            )
            previous_hash = previous.event_hash if previous else ""

            payload = {
                "reference": event.reference,
                "campaign_run": event.campaign_run_id.reference,
                "email": event.email_normalized or "",
                "event_type": event.event_type,
                "event_timestamp": event.event_timestamp.isoformat()
                if event.event_timestamp
                else "",
                "attempt": event.attempt_number,
                "provider_message_id": event.provider_message_id or "",
                "previous_event_hash": previous_hash,
            }
            encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
            event_hash = hashlib.sha256(encoded).hexdigest()

            super(NewsletterSendEvent, event).write(
                {
                    "previous_event_hash": previous_hash,
                    "payload_hash": hashlib.sha256(
                        json.dumps(payload, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "event_hash": event_hash,
                }
            )

    def verify_integrity(self):
        """Recompute each event's hash from its stored fields and compare
        against the stored hash. Returns True only if every event in
        ``self`` still matches.
        """
        for event in self:
            payload = {
                "reference": event.reference,
                "campaign_run": event.campaign_run_id.reference,
                "email": event.email_normalized or "",
                "event_type": event.event_type,
                "event_timestamp": event.event_timestamp.isoformat()
                if event.event_timestamp
                else "",
                "attempt": event.attempt_number,
                "provider_message_id": event.provider_message_id or "",
                "previous_event_hash": event.previous_event_hash or "",
            }
            encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
            if hashlib.sha256(encoded).hexdigest() != event.event_hash:
                return False
        return True

    # The retention engine may still stamp retention_policy_id/retain_until/
    # retention_state/legal_hold on an otherwise-immutable send event -
    # none of those touch the recorded event content.
    _RETENTION_MIXIN_FIELDS = {
        "retention_policy_id",
        "retention_start_at",
        "retain_until",
        "retention_state",
        "legal_hold",
        "retention_basis",
    }

    def write(self, vals):
        if set(vals) - self._RETENTION_MIXIN_FIELDS:
            raise UserError(_("Send events are immutable and cannot be modified."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Send events cannot be deleted."))
