from odoo import api, fields, models


class NewsletterRetentionPreviewWizard(models.TransientModel):
    _name = "newsletter.retention.preview.wizard"
    _description = "Preview Retention Policy Impact"

    policy_id = fields.Many2one("newsletter.retention.policy", required=True)
    preview_result = fields.Text(readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        policy_id = self.env.context.get("active_id") or self.env.context.get("default_policy_id")
        if policy_id and "policy_id" in fields_list:
            res["policy_id"] = policy_id
        return res

    def action_preview(self):
        from ..services import retention_service

        self.ensure_one()
        counts = retention_service.process_policy(self.env, self.policy_id, dry_run=True)

        lines = [f"Dry-run preview for policy: {self.policy_id.name}", ""]
        for key, value in counts.items():
            lines.append(f"{key}: {value}")

        self.write({"preview_result": "\n".join(lines)})

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
