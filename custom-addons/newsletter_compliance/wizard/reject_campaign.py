from odoo import api, fields, models


class NewsletterRejectCampaignWizard(models.TransientModel):
    _name = "newsletter.reject.campaign.wizard"
    _description = "Reject Newsletter Campaign"

    mailing_id = fields.Many2one(
        "mailing.mailing",
        required=True,
        ondelete="cascade",
    )

    reason = fields.Text(required=True)
    comments = fields.Text(string="Reviewer Comments")

    return_to = fields.Selection(
        [
            ("draft", "Draft"),
            ("content_review", "Content Review"),
        ],
        required=True,
        default="draft",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        mailing_id = self.env.context.get("active_id")
        if mailing_id and "mailing_id" in fields_list:
            res["mailing_id"] = mailing_id
        return res

    def action_confirm(self):
        self.ensure_one()
        self.mailing_id.action_reject(
            reason=self.reason,
            comments=self.comments,
            return_to=self.return_to,
        )
        return {"type": "ir.actions.act_window_close"}
