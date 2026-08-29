from odoo import api, fields, models
from markupsafe import Markup, escape


class ResPartner(models.Model):
    _inherit = "res.partner"

    # -- Bulk Email blueprint §3: segmentation fields for mailing_domain
    # filters. Country/Language are already native res.partner fields, so
    # only the genuinely missing dimensions are added here.
    newsletter_recipient_type = fields.Selection(
        [
            ("individual", "Individual"),
            ("business", "Business"),
            ("partner_org", "Partner Organization"),
            ("prospect", "Prospect"),
            ("employee", "Employee"),
            ("other", "Other"),
        ],
        string="Recipient Type",
    )
    newsletter_segment = fields.Char(
        string="Segment",
        help="Free-text segmentation tag usable in a mailing's recipient "
        "domain filter (e.g. \"Enterprise\", \"SMB\", \"VIP\").",
    )
    newsletter_region = fields.Char(
        string="Region",
        help="Organizational region, distinct from Country (e.g. "
        "\"EMEA\", \"APAC\") - usable in a mailing's recipient domain filter.",
    )

    newsletter_eligibility_summary = fields.Html(
        string="Communication Eligibility",
        compute="_compute_newsletter_eligibility_summary",
        sanitize=False,
    )

    consent_record_ids = fields.One2many(
        "newsletter.consent.record",
        "partner_id",
        string="Consent Records",
    )

    consent_count = fields.Integer(
        compute="_compute_newsletter_compliance_counts",
    )

    suppression_entry_ids = fields.One2many(
        "newsletter.suppression.entry",
        "partner_id",
        string="Suppression Entries",
    )

    suppression_count = fields.Integer(
        compute="_compute_newsletter_compliance_counts",
    )

    active_consent_count = fields.Integer(
        compute="_compute_newsletter_compliance_counts",
    )

    active_suppression_count = fields.Integer(
        compute="_compute_newsletter_compliance_counts",
    )

    @api.depends("consent_record_ids.status", "suppression_entry_ids.active")
    def _compute_newsletter_compliance_counts(self):
        for partner in self:
            partner.consent_count = len(partner.consent_record_ids)
            partner.suppression_count = len(partner.suppression_entry_ids)
            partner.active_consent_count = len(
                partner.consent_record_ids.filtered(lambda r: r.status == "active")
            )
            partner.active_suppression_count = len(
                partner.suppression_entry_ids.filtered(lambda r: r.active)
            )

    @api.depends(
        "consent_record_ids.status",
        "consent_record_ids.purpose_id",
        "suppression_entry_ids.active",
        "suppression_entry_ids.scope",
        "suppression_entry_ids.purpose_id",
    )
    def _compute_newsletter_eligibility_summary(self):
        """Bulk Email blueprint §6: the per-purpose Allowed/Suppressed/No
        Consent grid mocked up on the Contact screen - computed live rather
        than stored, since it's a read-only reflection of consent/
        suppression state that changes constantly.
        """
        purposes = self.env["newsletter.consent.purpose"].search([("active", "=", True)])
        for partner in self:
            active_purpose_ids = set(
                partner.consent_record_ids.filtered(lambda r: r.status == "active").mapped(
                    "purpose_id.id"
                )
            )
            active_suppressions = partner.suppression_entry_ids.filtered("active")
            globally_suppressed = any(s.scope == "global" for s in active_suppressions)
            suppressed_purpose_ids = set(
                active_suppressions.filtered(lambda s: s.scope == "purpose").mapped(
                    "purpose_id.id"
                )
            )

            rows = []
            for purpose in purposes:
                if globally_suppressed or purpose.id in suppressed_purpose_ids:
                    status_html = '<span style="color:#a94442;">&#10007; Suppressed</span>'
                elif purpose.id in active_purpose_ids:
                    status_html = '<span style="color:#3c763d;">&#10003; Allowed</span>'
                else:
                    status_html = '<span style="color:#a94442;">&#10007; No Consent</span>'
                rows.append(f"<tr><td>{escape(purpose.name)}</td><td>{status_html}</td></tr>")

            if rows:
                table = (
                    '<table class="table table-sm">'
                    "<thead><tr><th>Purpose</th><th>Status</th></tr></thead>"
                    f"<tbody>{''.join(rows)}</tbody></table>"
                )
            else:
                table = "<p>No consent purposes configured.</p>"
            partner.newsletter_eligibility_summary = Markup(table)

    def action_view_newsletter_consents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Consent Records",
            "res_model": "newsletter.consent.record",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    def action_view_newsletter_suppressions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Suppression Entries",
            "res_model": "newsletter.suppression.entry",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id, "search_default_filter_active": 0},
        }

    def action_view_newsletter_reputation(self):
        self.ensure_one()
        reputation = self.env["newsletter.delivery.reputation"].search(
            [("partner_id", "=", self.id)], limit=1
        )
        action = {
            "type": "ir.actions.act_window",
            "name": "Newsletter Deliverability",
            "res_model": "newsletter.delivery.reputation",
        }
        if reputation:
            action.update({"view_mode": "form", "res_id": reputation.id})
        else:
            action.update({"view_mode": "list,form", "domain": [("partner_id", "=", self.id)]})
        return action

    def action_view_newsletter_send_history(self):
        """Derived from newsletter.recipient.eligibility - every campaign
        decision for this partner, with dispatch/delivery outcome and the
        consent/suppression basis, in one place (FR-27 recipient
        reconstruction). Not a separately maintained history table.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Send History",
            "res_model": "newsletter.recipient.eligibility",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
        }
