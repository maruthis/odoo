from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NewsletterWithdrawConsentWizard(models.TransientModel):
    _name = "newsletter.withdraw.consent.wizard"
    _description = "Withdraw Newsletter Consent"

    consent_id = fields.Many2one(
        "newsletter.consent.record",
        required=True,
        ondelete="cascade",
    )

    withdrawal_date = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
    )

    withdrawal_source = fields.Selection(
        [
            ("unsubscribe", "Unsubscribe Link"),
            ("email", "Email Request"),
            ("phone", "Phone Request"),
            ("portal", "Preference Centre"),
            ("manual", "Authorized Manual Action"),
            ("api", "API"),
            ("other", "Other"),
        ],
        required=True,
        default="manual",
    )

    reason = fields.Text(required=True)

    create_suppression = fields.Boolean(
        string="Create Suppression?",
        default=True,
    )

    suppression_scope = fields.Selection(
        [
            ("global", "Global"),
            ("purpose", "Consent Purpose"),
            ("mailing_list", "Mailing List"),
        ],
        default="purpose",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        consent_id = self.env.context.get("active_id")
        if consent_id and "consent_id" in fields_list:
            res["consent_id"] = consent_id
        return res

    def action_confirm(self):
        self.ensure_one()

        if self.consent_id.status != "active":
            raise UserError(_("Only an active consent can be withdrawn."))

        self.consent_id.write(
            {
                "status": "withdrawn",
                "withdrawn_at": self.withdrawal_date,
                "withdrawal_reason": self.reason,
                "withdrawal_source": self.withdrawal_source,
            }
        )

        self.consent_id.message_post(
            body=_(
                "Consent withdrawn on %(date)s via %(source)s. Reason: %(reason)s",
                date=self.withdrawal_date,
                source=self.withdrawal_source,
                reason=self.reason,
            )
        )

        if self.create_suppression:
            reason = self.env["newsletter.suppression.reason"].search(
                [("code", "=", "UNSUBSCRIBE")], limit=1
            )
            vals = {
                "partner_id": self.consent_id.partner_id.id,
                "scope": self.suppression_scope,
                "reason_id": reason.id,
                "source": "unsubscribe",
                "details": self.reason,
                "company_id": self.consent_id.company_id.id,
            }
            if self.suppression_scope == "purpose":
                vals["purpose_id"] = self.consent_id.purpose_id.id
            self.env["newsletter.suppression.entry"].create(vals)

        return {"type": "ir.actions.act_window_close"}
