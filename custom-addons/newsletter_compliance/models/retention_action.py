from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NewsletterRetentionAction(models.Model):
    _name = "newsletter.retention.action"
    _description = "Newsletter Retention Action Ledger"
    _order = "executed_at desc, id desc"
    _rec_name = "reference"

    reference = fields.Char(readonly=True, copy=False, default="New")

    policy_id = fields.Many2one("newsletter.retention.policy", index=True, ondelete="set null")
    model_name = fields.Char(required=True, index=True)
    record_reference = fields.Char(required=True)
    record_res_id = fields.Integer()

    action_type = fields.Selection(
        [
            ("retain", "Retain"),
            ("review", "Manual Review"),
            ("pseudonymize", "Pseudonymize"),
            ("anonymize", "Anonymize"),
            ("purge_payload", "Remove Raw Payload"),
            ("delete", "Delete"),
            ("hold_blocked", "Blocked by Legal Hold"),
        ],
        required=True,
    )

    executed_at = fields.Datetime(default=fields.Datetime.now, required=True)
    executed_by_id = fields.Many2one(
        "res.users", default=lambda self: self.env.user, required=True
    )

    previous_identity_state = fields.Char()
    new_identity_state = fields.Char()
    legal_hold_checked = fields.Boolean(default=True)

    result = fields.Selection(
        [
            ("success", "Success"),
            ("failed", "Failed"),
            ("blocked", "Blocked"),
        ],
        required=True,
    )
    error_message = fields.Text()

    evidence_hash_before = fields.Char()
    evidence_hash_after = fields.Char()

    privacy_request_id = fields.Many2one(
        "newsletter.privacy.request", index=True, ondelete="set null"
    )
    dry_run = fields.Boolean(default=False)

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
                    self.env["ir.sequence"].next_by_code("newsletter.retention.action") or "New"
                )
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("Retention actions are immutable audit history."))

    def unlink(self):
        raise UserError(_("Retention actions cannot be deleted."))

    @api.model
    def _cron_monitor_retention_failures(self):
        """Raises/refreshes a single operational alert whenever the
        retention processor has left failed actions behind in the last
        day - it does not resolve on its own; an administrator investigates
        and resolves it once the underlying cause is fixed (R6 blueprint
        §26/§37).
        """
        import datetime

        from odoo import fields as odoo_fields

        since = odoo_fields.Datetime.now() - datetime.timedelta(days=1)
        failed_count = self.sudo().search_count(
            [("result", "=", "failed"), ("executed_at", ">=", since)]
        )
        if not failed_count:
            return
        self.env["newsletter.compliance.alert"]._create_or_update_alert(
            "retention_failure",
            "critical" if failed_count >= 5 else "warning",
            "failed_retention_actions",
            float(failed_count),
            0.0,
        )
