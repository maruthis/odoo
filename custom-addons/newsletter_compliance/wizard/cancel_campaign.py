from odoo import api, fields, models


class NewsletterCancelCampaignWizard(models.TransientModel):
    _name = "newsletter.cancel.campaign.wizard"
    _description = "Cancel Newsletter Campaign"

    mailing_id = fields.Many2one(
        "mailing.mailing",
        required=True,
        ondelete="cascade",
    )

    reason = fields.Text(required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        mailing_id = self.env.context.get("active_id")
        if mailing_id and "mailing_id" in fields_list:
            res["mailing_id"] = mailing_id
        return res

    def action_confirm(self):
        self.ensure_one()
        self.mailing_id.action_cancel_campaign(reason=self.reason)
        return {"type": "ir.actions.act_window_close"}
