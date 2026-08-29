from odoo import api, fields, models


class NewsletterPrivacyRequestExecuteWizard(models.TransientModel):
    _name = "newsletter.privacy.request.execute.wizard"
    _description = "Execute Privacy Request"

    privacy_request_id = fields.Many2one("newsletter.privacy.request", required=True)
    confirmation_text = fields.Char(
        default="I confirm this request should be executed as decided.", readonly=True
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = self.env.context.get("active_id") or self.env.context.get(
            "default_privacy_request_id"
        )
        if request_id and "privacy_request_id" in fields_list:
            res["privacy_request_id"] = request_id
        return res

    def action_confirm(self):
        self.ensure_one()
        self.privacy_request_id.action_execute()
        return {"type": "ir.actions.act_window_close"}
