import datetime

from odoo import api, fields, models


class NewsletterDeliveryReputation(models.Model):
    _name = "newsletter.delivery.reputation"
    _description = "Newsletter Recipient Delivery Reputation"
    _order = "email_normalized"
    _rec_name = "email_normalized"

    email_normalized = fields.Char(required=True, index=True)
    partner_id = fields.Many2one("res.partner", index=True, ondelete="set null")

    soft_bounce_count = fields.Integer(
        default=0,
        help="Current consecutive-within-window soft bounce count. Resets "
        "on successful delivery, or when a new soft bounce arrives after "
        "the reputation window has elapsed since the last one.",
    )
    lifetime_soft_bounce_count = fields.Integer(default=0)
    hard_bounce_count = fields.Integer(default=0)
    complaint_count = fields.Integer(default=0)

    last_soft_bounce_at = fields.Datetime()
    last_hard_bounce_at = fields.Datetime()
    last_delivery_at = fields.Datetime()
    last_complaint_at = fields.Datetime()

    reputation_state = fields.Selection(
        [
            ("good", "Good"),
            ("warning", "Warning"),
            ("suppressed", "Suppressed"),
        ],
        default="good",
        readonly=True,
    )

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _email_company_unique = models.Constraint(
        "unique(email_normalized, company_id)",
        "Only one reputation record per email per company.",
    )

    @api.model
    def _get_or_create(self, email_normalized, partner_id=False, company_id=False):
        company_id = company_id or self.env.company.id
        reputation = self.sudo().search(
            [("email_normalized", "=", email_normalized), ("company_id", "=", company_id)],
            limit=1,
        )
        if not reputation:
            reputation = self.sudo().create(
                {
                    "email_normalized": email_normalized,
                    "partner_id": partner_id or False,
                    "company_id": company_id,
                }
            )
        elif partner_id and not reputation.partner_id:
            reputation.write({"partner_id": partner_id})
        return reputation

    def record_delivered(self, event_timestamp):
        self.ensure_one()
        self.write(
            {
                "last_delivery_at": event_timestamp,
                "soft_bounce_count": 0,
                "reputation_state": "good" if self.reputation_state != "suppressed" else "suppressed",
            }
        )

    def record_soft_bounce(self, event_timestamp, window_days):
        """Returns True if this soft bounce pushed the count to/over
        threshold territory (caller decides the actual threshold)."""
        self.ensure_one()

        window_expired = bool(
            self.last_soft_bounce_at
            and fields.Datetime.to_datetime(event_timestamp)
            - fields.Datetime.to_datetime(self.last_soft_bounce_at)
            > datetime.timedelta(days=window_days)
        )
        new_count = 1 if window_expired else self.soft_bounce_count + 1

        self.write(
            {
                "soft_bounce_count": new_count,
                "lifetime_soft_bounce_count": self.lifetime_soft_bounce_count + 1,
                "last_soft_bounce_at": event_timestamp,
                "reputation_state": "warning" if self.reputation_state == "good" else self.reputation_state,
            }
        )
        return new_count

    def record_hard_bounce(self, event_timestamp):
        self.ensure_one()
        self.write(
            {
                "hard_bounce_count": self.hard_bounce_count + 1,
                "last_hard_bounce_at": event_timestamp,
                "reputation_state": "suppressed",
            }
        )

    def record_complaint(self, event_timestamp):
        self.ensure_one()
        self.write(
            {
                "complaint_count": self.complaint_count + 1,
                "last_complaint_at": event_timestamp,
                "reputation_state": "suppressed",
            }
        )
