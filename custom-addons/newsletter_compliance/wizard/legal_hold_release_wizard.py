from odoo import api, fields, models


class NewsletterLegalHoldReleaseWizard(models.TransientModel):
    _name = "newsletter.legal.hold.release.wizard"
    _description = "Release Legal Hold"

    legal_hold_id = fields.Many2one("newsletter.legal.hold", required=True)
    reason = fields.Text(required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        hold_id = self.env.context.get("active_id") or self.env.context.get("default_legal_hold_id")
        if hold_id and "legal_hold_id" in fields_list:
            res["legal_hold_id"] = hold_id
        return res

    def action_confirm(self):
        self.ensure_one()
        self.legal_hold_id.action_release(reason=self.reason)
        return {"type": "ir.actions.act_window_close"}
