from odoo import fields, models, _
from odoo.exceptions import UserError


class NewsletterCampaignOutcomeAdjustment(models.Model):
    _name = "newsletter.campaign.outcome.adjustment"
    _description = "Late Delivery Event Adjustment"
    _order = "create_date desc, id desc"

    outcome_id = fields.Many2one(
        "newsletter.campaign.outcome", required=True, index=True, ondelete="cascade"
    )
    event_type = fields.Char(required=True)
    provider_event_id = fields.Char()
    recorded_at = fields.Datetime(default=fields.Datetime.now, required=True)
    note = fields.Text()

    def write(self, vals):
        raise UserError(_("Outcome adjustments are immutable."))

    def unlink(self):
        raise UserError(_("Outcome adjustments cannot be deleted."))
