from odoo import api, models


class MailBlacklist(models.Model):
    _inherit = "mail.blacklist"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        if self.env.context.get("newsletter_skip_blacklist_sync"):
            return records

        reason = self.env.ref(
            "newsletter_compliance.suppression_reason_global_opt_out", raise_if_not_found=False
        )
        if not reason:
            return records

        SuppressionEntry = self.env["newsletter.suppression.entry"].sudo()
        for record in records:
            partner = self.env["res.partner"].sudo().search(
                [("email_normalized", "=", record.email)], limit=1
            )
            if not partner:
                continue

            existing = SuppressionEntry.search(
                [
                    ("partner_id", "=", partner.id),
                    ("scope", "=", "global"),
                    ("reason_id", "=", reason.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if existing:
                continue

            SuppressionEntry.with_context(newsletter_skip_blacklist_sync=True).create(
                {
                    "partner_id": partner.id,
                    "scope": "global",
                    "reason_id": reason.id,
                    "source": "odoo_blacklist",
                    "details": "Created from a native Odoo global blacklist entry.",
                }
            )

        return records
