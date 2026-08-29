from odoo import api, fields, models


class NewsletterResetCampaignWizard(models.TransientModel):
    _name = "newsletter.reset.campaign.wizard"
    _description = "Return Newsletter Campaign to Draft"

    mailing_id = fields.Many2one(
        "mailing.mailing",
        required=True,
        ondelete="cascade",
    )

    reason = fields.Selection(
        [
            ("content_correction", "Content Correction"),
            ("recipient_change", "Recipient Segment Change"),
            ("consent_purpose_correction", "Consent Purpose Correction"),
            ("sender_correction", "Sender Correction"),
            ("postponed", "Campaign Postponed"),
            ("other", "Other"),
        ],
        required=True,
    )

    comments = fields.Text()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        mailing_id = self.env.context.get("active_id")
        if mailing_id and "mailing_id" in fields_list:
            res["mailing_id"] = mailing_id
        return res

    def action_confirm(self):
        self.ensure_one()
        reason_label = dict(self._fields["reason"].selection).get(self.reason)
        reason_text = reason_label if not self.comments else f"{reason_label}: {self.comments}"
        self.mailing_id.action_reset_to_draft(reason=reason_text)
        return {"type": "ir.actions.act_window_close"}
