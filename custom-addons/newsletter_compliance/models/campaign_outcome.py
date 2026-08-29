import hashlib
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _safe_ratio(numerator, denominator):
    if not denominator:
        return 0.0
    return numerator / denominator


class NewsletterCampaignOutcome(models.Model):
    _name = "newsletter.campaign.outcome"
    _description = "Newsletter Campaign Outcome Summary"
    _order = "create_date desc, id desc"
    _rec_name = "reference"

    reference = fields.Char(readonly=True, copy=False, default="New")

    # archive_id is only known once the run completes and archives -
    # the outcome itself is created at execution start, so live delivery
    # feedback can be monitored (and alerted on) while sending is still
    # in progress, not only after the fact.
    archive_id = fields.Many2one(
        "newsletter.campaign.archive", index=True, ondelete="restrict", copy=False
    )
    campaign_run_id = fields.Many2one(
        "newsletter.campaign.run", required=True, index=True, ondelete="restrict"
    )
    mailing_id = fields.Many2one(
        "mailing.mailing", required=True, index=True, ondelete="restrict"
    )

    sent_count = fields.Integer(default=0)
    accepted_count = fields.Integer(default=0)
    delivered_count = fields.Integer(default=0)
    delivery_delayed_count = fields.Integer(default=0)

    soft_bounced_count = fields.Integer(default=0)
    hard_bounced_count = fields.Integer(default=0)
    unknown_bounce_count = fields.Integer(default=0)

    complained_count = fields.Integer(default=0)
    unsubscribed_count = fields.Integer(default=0)
    provider_rejected_count = fields.Integer(default=0)

    delivery_rate = fields.Float(compute="_compute_rates")
    bounce_rate = fields.Float(compute="_compute_rates")
    hard_bounce_rate = fields.Float(compute="_compute_rates")
    complaint_rate = fields.Float(compute="_compute_rates")
    unsubscribe_rate = fields.Float(compute="_compute_rates")

    threshold_state = fields.Selection(
        [
            ("healthy", "Healthy"),
            ("warning", "Warning"),
            ("critical", "Critical"),
        ],
        default="healthy",
        readonly=True,
    )

    outcome_observation_started_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    outcome_observation_until = fields.Datetime(readonly=True)

    finalized = fields.Boolean(default=False, readonly=True)
    finalized_at = fields.Datetime(readonly=True)
    finalized_by_id = fields.Many2one("res.users", readonly=True)
    outcome_hash = fields.Char(readonly=True)

    adjustment_ids = fields.One2many(
        "newsletter.campaign.outcome.adjustment", "outcome_id", string="Late Adjustments"
    )

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("newsletter.campaign.outcome") or "New"
                )
        return super().create(vals_list)

    @api.depends(
        "sent_count",
        "delivered_count",
        "soft_bounced_count",
        "hard_bounced_count",
        "complained_count",
        "unsubscribed_count",
    )
    def _compute_rates(self):
        for outcome in self:
            outcome.delivery_rate = _safe_ratio(outcome.delivered_count, outcome.sent_count)
            outcome.bounce_rate = _safe_ratio(
                outcome.soft_bounced_count + outcome.hard_bounced_count, outcome.sent_count
            )
            outcome.hard_bounce_rate = _safe_ratio(outcome.hard_bounced_count, outcome.sent_count)
            outcome.complaint_rate = _safe_ratio(outcome.complained_count, outcome.sent_count)
            outcome.unsubscribe_rate = _safe_ratio(outcome.unsubscribed_count, outcome.sent_count)

    def _apply_event_count(self, event_type):
        """Increment the count field matching a canonical delivery event
        type. Called live as provider events are processed - this is what
        makes bounce/complaint thresholds observable during an in-progress
        campaign, not only after completion.
        """
        self.ensure_one()
        field_by_event_type = {
            "accepted": "accepted_count",
            "delivered": "delivered_count",
            "delivery_delayed": "delivery_delayed_count",
            "complaint": "complained_count",
            "unsubscribe": "unsubscribed_count",
            "provider_rejected": "provider_rejected_count",
            "provider_dropped": "provider_rejected_count",
        }
        field_name = field_by_event_type.get(event_type)
        if field_name:
            self.write({field_name: self[field_name] + 1})

    def _apply_bounce_count(self, classification):
        self.ensure_one()
        field_name = {
            "hard": "hard_bounced_count",
            "soft": "soft_bounced_count",
        }.get(classification, "unknown_bounce_count")
        self.write({field_name: self[field_name] + 1})

    def _build_outcome_hash(self):
        self.ensure_one()
        payload = {
            "campaign_run": self.campaign_run_id.reference,
            "sent_count": self.sent_count,
            "delivered_count": self.delivered_count,
            "soft_bounced_count": self.soft_bounced_count,
            "hard_bounced_count": self.hard_bounced_count,
            "complained_count": self.complained_count,
            "unsubscribed_count": self.unsubscribed_count,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else "",
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def action_finalize(self):
        for outcome in self:
            if outcome.finalized:
                continue
            outcome.write(
                {
                    "finalized": True,
                    "finalized_at": fields.Datetime.now(),
                    "finalized_by_id": self.env.user.id,
                }
            )
            outcome.write({"outcome_hash": outcome._build_outcome_hash()})

    def verify_integrity(self):
        """True only if the outcome is either unfinalized (nothing to
        verify yet) or its stored hash still matches its current data.
        """
        for outcome in self:
            if not outcome.finalized:
                continue
            if outcome._build_outcome_hash() != outcome.outcome_hash:
                return False
        return True

    def record_late_adjustment(self, event_type, provider_event_id=False, note=False):
        """A provider event arriving after finalization must never silently
        rewrite locked evidence - it becomes a linked adjustment instead.
        """
        self.ensure_one()
        return self.env["newsletter.campaign.outcome.adjustment"].sudo().create(
            {
                "outcome_id": self.id,
                "event_type": event_type,
                "provider_event_id": provider_event_id,
                "note": note,
            }
        )

    @api.model
    def _cron_finalize_due_outcomes(self):
        import datetime

        from ..services import config_service

        window_hours = config_service.get_outcome_finalization_window_hours(self.env)
        cutoff = fields.Datetime.now() - datetime.timedelta(hours=window_hours)

        due = self.search(
            [
                ("finalized", "=", False),
                ("campaign_run_id.execution_completed_at", "!=", False),
                ("campaign_run_id.execution_completed_at", "<=", cutoff),
            ]
        )
        due.action_finalize()

    def write(self, vals):
        if self.env.context.get("skip_outcome_finalize_guard"):
            return super().write(vals)
        if self.filtered("finalized") and set(vals) - {
            "finalized",
            "finalized_at",
            "finalized_by_id",
            "outcome_hash",
            "archive_id",
        }:
            raise UserError(_("This campaign outcome has been finalized and cannot be changed."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Campaign outcomes cannot be deleted."))
