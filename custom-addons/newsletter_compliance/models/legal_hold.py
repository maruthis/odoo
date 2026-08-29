from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NewsletterLegalHold(models.Model):
    _name = "newsletter.legal.hold"
    _description = "Newsletter Legal Hold"
    _order = "start_at desc, id desc"
    _inherit = ["mail.thread"]

    reference = fields.Char(readonly=True, copy=False, default="New")
    name = fields.Char(required=True, tracking=True)
    reason = fields.Text(required=True)
    legal_reference = fields.Char(string="Case / Legal Reference")

    start_at = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    released_at = fields.Datetime(readonly=True)

    status = fields.Selection(
        [
            ("active", "Active"),
            ("released", "Released"),
        ],
        default="active",
        required=True,
        tracking=True,
    )

    owner_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, tracking=True
    )
    approved_by_id = fields.Many2one("res.users", tracking=True)

    scope_type = fields.Selection(
        [
            ("campaign", "Campaign"),
            ("campaign_run", "Campaign Run"),
            ("recipient", "Recipient"),
            ("date_range", "Date Range"),
            ("company", "Entire Company"),
        ],
        required=True,
        default="recipient",
    )

    scope_mailing_ids = fields.Many2many("mailing.mailing", string="Campaigns")
    scope_campaign_run_ids = fields.Many2many("newsletter.campaign.run", string="Campaign Runs")
    scope_partner_ids = fields.Many2many("res.partner", string="Recipients")
    scope_date_from = fields.Date()
    scope_date_until = fields.Date()

    released_by_id = fields.Many2one("res.users", readonly=True)
    release_reason = fields.Text(readonly=True)

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
                    self.env["ir.sequence"].next_by_code("newsletter.legal.hold") or "New"
                )
        records = super().create(vals_list)
        for record in records:
            record.message_post(
                body=_(
                    "Legal hold created by %(user)s. Reason: %(reason)s",
                    user=record.owner_id.display_name,
                    reason=record.reason,
                )
            )
        return records

    def action_release(self, reason):
        for hold in self:
            if hold.status != "active":
                raise UserError(_("This hold is not active."))
            if not reason:
                raise UserError(_("A release reason is required."))

            hold.write(
                {
                    "status": "released",
                    "released_at": fields.Datetime.now(),
                    "released_by_id": self.env.user.id,
                    "release_reason": reason,
                }
            )
            hold.message_post(
                body=_(
                    "Legal hold released by %(user)s. Reason: %(reason)s. "
                    "Affected records re-enter normal retention evaluation "
                    "on the next scheduled run.",
                    user=self.env.user.display_name,
                    reason=reason,
                )
            )

    def is_partner_held(self, partner_id):
        """True if any active hold in ``self`` covers this partner, either
        by direct recipient scope or by company-wide scope."""
        for hold in self.filtered(lambda h: h.status == "active"):
            if hold.scope_type == "company":
                return True
            if hold.scope_type == "recipient" and partner_id in hold.scope_partner_ids.ids:
                return True
        return False

    def is_mailing_held(self, mailing_id):
        for hold in self.filtered(lambda h: h.status == "active"):
            if hold.scope_type == "company":
                return True
            if hold.scope_type == "campaign" and mailing_id in hold.scope_mailing_ids.ids:
                return True
        return False

    def is_campaign_run_held(self, campaign_run_id):
        for hold in self.filtered(lambda h: h.status == "active"):
            if hold.scope_type == "company":
                return True
            if hold.scope_type == "campaign_run" and campaign_run_id in hold.scope_campaign_run_ids.ids:
                return True
        return False
