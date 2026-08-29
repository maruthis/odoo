from odoo import api, fields, models


class NewsletterCancelExecutionWizard(models.TransientModel):
    _name = "newsletter.cancel.execution.wizard"
    _description = "Cancel Newsletter Campaign Execution"

    campaign_run_id = fields.Many2one(
        "newsletter.campaign.run",
        required=True,
        ondelete="cascade",
    )

    reason = fields.Text(required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        run_id = self.env.context.get("active_id") or self.env.context.get(
            "default_campaign_run_id"
        )
        if run_id and "campaign_run_id" in fields_list:
            res["campaign_run_id"] = run_id
        return res

    def action_confirm(self):
        self.ensure_one()
        self.campaign_run_id.action_cancel_execution(reason=self.reason)
        return {"type": "ir.actions.act_window_close"}
