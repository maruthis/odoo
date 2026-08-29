from odoo import api, fields, models, _
from odoo.exceptions import UserError


class NewsletterReinstateSuppressionWizard(models.TransientModel):
    _name = "newsletter.reinstate.suppression.wizard"
    _description = "Reinstate Newsletter Suppression"

    suppression_id = fields.Many2one(
        "newsletter.suppression.entry",
        required=True,
        ondelete="cascade",
    )

    reinstatement_reason = fields.Text(required=True)
    evidence_reference = fields.Char(string="Evidence / Reference")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        suppression_id = self.env.context.get("active_id")
        if suppression_id and "suppression_id" in fields_list:
            res["suppression_id"] = suppression_id
        return res

    def action_confirm(self):
        self.ensure_one()

        if not self.env.user.has_group(
            "newsletter_compliance.group_newsletter_compliance_admin"
        ):
            raise UserError(
                _("Only a Compliance Administrator can reinstate a suppression.")
            )

        if not self.suppression_id.active:
            raise UserError(_("This suppression is already reinstated."))

        if not self.suppression_id.reason_id.allow_reinstatement:
            raise UserError(
                _("This suppression reason does not allow reinstatement.")
            )

        reason_text = self.reinstatement_reason
        if self.evidence_reference:
            reason_text = _(
                "%(reason)s (Evidence: %(evidence)s)",
                reason=self.reinstatement_reason,
                evidence=self.evidence_reference,
            )

        self.suppression_id.write(
            {
                "active": False,
                "reinstated_at": fields.Datetime.now(),
                "reinstated_by_id": self.env.user.id,
                "reinstatement_reason": reason_text,
            }
        )

        self.suppression_id.message_post(
            body=_(
                "Suppression reinstated by %(user)s. Reason: %(reason)s",
                user=self.env.user.name,
                reason=reason_text,
            )
        )

        return {"type": "ir.actions.act_window_close"}
