from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NewsletterManualRetentionWizard(models.TransientModel):
    _name = "newsletter.manual.retention.wizard"
    _description = "Manual Retention Run (Two-Person Control)"

    policy_id = fields.Many2one("newsletter.retention.policy", required=True)
    prepared_by_id = fields.Many2one(
        "res.users", default=lambda self: self.env.user, required=True, readonly=True
    )
    approved_by_id = fields.Many2one("res.users", required=True)
    reason = fields.Text(required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        policy_id = self.env.context.get("active_id") or self.env.context.get("default_policy_id")
        if policy_id and "policy_id" in fields_list:
            res["policy_id"] = policy_id
        return res

    def action_execute(self):
        from ..services import retention_service

        self.ensure_one()

        if self.approved_by_id == self.prepared_by_id:
            raise UserError(
                _("The approver must be a different person than whoever prepared this run.")
            )
        if not self.approved_by_id.has_group(
            "newsletter_compliance.group_newsletter_compliance_admin"
        ):
            raise UserError(_("The approver must be a Compliance Administrator."))

        retention_service.process_policy(self.env, self.policy_id, dry_run=False)

        return {"type": "ir.actions.act_window_close"}
