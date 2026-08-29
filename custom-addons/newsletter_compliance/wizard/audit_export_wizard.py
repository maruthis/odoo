from odoo import api, fields, models


class NewsletterAuditExportWizard(models.TransientModel):
    _name = "newsletter.audit.export.wizard"
    _description = "Generate Campaign Audit Export"

    campaign_run_id = fields.Many2one("newsletter.campaign.run", required=True)
    masked = fields.Boolean(
        default=True, string="Mask Personal Data",
        help="Full (unmasked) exports require the Compliance Administrator role.",
    )
    purpose = fields.Text()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        run_id = self.env.context.get("active_id") or self.env.context.get(
            "default_campaign_run_id"
        )
        if run_id and "campaign_run_id" in fields_list:
            res["campaign_run_id"] = run_id
        return res

    def action_generate(self):
        self.ensure_one()

        masked = self.masked
        if not masked and not self.env.user.has_group(
            "newsletter_compliance.group_newsletter_compliance_admin"
        ):
            # fail safe to masked rather than raise, so the export still
            # succeeds but never over-shares PII to an unprivileged user
            masked = True

        export = self.env["newsletter.audit.export"].create(
            {
                "export_type": "campaign",
                "campaign_run_id": self.campaign_run_id.id,
                "masked": masked,
                "purpose": self.purpose,
            }
        )
        export.action_generate_campaign_package()

        return {
            "type": "ir.actions.act_window",
            "res_model": "newsletter.audit.export",
            "res_id": export.id,
            "view_mode": "form",
            "target": "current",
        }
