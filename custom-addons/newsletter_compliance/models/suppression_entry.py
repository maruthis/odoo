from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

GLOBAL_BLACKLIST_CATEGORIES = {"bounce", "complaint"}
GLOBAL_BLACKLIST_CODES = {"GLOBAL_OPT_OUT"}


class NewsletterSuppressionEntry(models.Model):
    _name = "newsletter.suppression.entry"
    _description = "Newsletter Suppression Entry"
    _inherit = ["mail.thread", "mail.activity.mixin", "newsletter.retention.mixin"]
    _order = "effective_from desc"

    reference = fields.Char(
        readonly=True,
        copy=False,
        default="New",
    )

    partner_id = fields.Many2one(
        "res.partner",
        ondelete="set null",
        index=True,
        tracking=True,
        help="Cleared on pseudonymization/erasure - the email_hash token "
        "remains so the opt-out still matches a re-imported email.",
    )

    email_normalized = fields.Char(
        readonly=True,
        index=True,
    )

    email_hash = fields.Char(
        readonly=True,
        index=True,
        help="HMAC(email_normalized) - populated at creation and retained "
        "even after the plain email is erased, so a re-imported copy of "
        "the same address still matches this suppression (R6 section 56).",
    )

    identity_state = fields.Selection(
        [
            ("identified", "Identified"),
            ("pseudonymized", "Pseudonymized"),
            ("anonymized", "Anonymized"),
        ],
        default="identified",
        required=True,
        readonly=True,
    )
    pseudonymized_at = fields.Datetime(readonly=True)
    pseudonymized_by_id = fields.Many2one("res.users", readonly=True)
    pseudonymization_reference = fields.Char(readonly=True)

    scope = fields.Selection(
        [
            ("global", "Global"),
            ("brand", "Brand"),
            ("purpose", "Consent Purpose"),
            ("mailing_list", "Mailing List"),
            ("campaign", "Campaign"),
        ],
        required=True,
        default="global",
        tracking=True,
    )

    brand_id = fields.Many2one(
        "newsletter.campaign.brand",
        ondelete="restrict",
        help="Blocks every campaign sent under this brand, across all "
        "purposes - narrower than Global, broader than Purpose.",
    )

    purpose_id = fields.Many2one(
        "newsletter.consent.purpose",
        ondelete="restrict",
    )

    mailing_list_id = fields.Many2one(
        "mailing.list",
        ondelete="restrict",
    )

    campaign_mailing_id = fields.Many2one(
        "mailing.mailing",
        ondelete="restrict",
        help="Blocks only this one specific campaign - the narrowest scope "
        "(e.g. \"do not resend me this particular newsletter\" without "
        "opting out of the purpose entirely).",
    )

    reason_id = fields.Many2one(
        "newsletter.suppression.reason",
        required=True,
        ondelete="restrict",
        tracking=True,
    )

    effective_from = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )

    effective_until = fields.Datetime(tracking=True)

    active = fields.Boolean(
        default=True,
        tracking=True,
    )

    source = fields.Selection(
        [
            ("unsubscribe", "Unsubscribe"),
            ("bounce", "Bounce"),
            ("complaint", "Complaint"),
            ("manual", "Manual"),
            ("api", "API"),
            ("compliance", "Compliance"),
            ("odoo_blacklist", "Odoo Blacklist Sync"),
            ("other", "Other"),
        ],
        required=True,
    )

    source_event_id = fields.Many2one(
        "newsletter.send.event",
        string="Source Send Event",
        ondelete="set null",
    )
    provider_event_id = fields.Char(string="Source Provider Event ID")

    details = fields.Text()

    evidence_attachment_id = fields.Many2one(
        "ir.attachment",
        ondelete="restrict",
    )

    reinstated_at = fields.Datetime(readonly=True)

    reinstated_by_id = fields.Many2one(
        "res.users",
        readonly=True,
    )

    reinstatement_reason = fields.Text(readonly=True)

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model
    def _normalize_email(self, email):
        return (email or "").strip().lower()

    @api.model_create_multi
    def create(self, vals_list):
        from ..services import pseudonymization_service

        for vals in vals_list:
            partner = self.env["res.partner"].browse(vals.get("partner_id"))

            email_normalized = self._normalize_email(partner.email)
            vals["email_normalized"] = email_normalized
            vals["email_hash"] = pseudonymization_service.hmac_token(self.env, email_normalized)

            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code(
                        "newsletter.suppression.entry"
                    )
                    or "New"
                )

        records = super().create(vals_list)
        records._sync_blacklist()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {"scope", "reason_id", "active"}.intersection(vals):
            self._sync_blacklist()
        return result

    def unlink(self):
        raise UserError(
            _(
                "Suppression records are retained as compliance history. "
                "Reinstate the recipient instead."
            )
        )

    def _sync_blacklist(self):
        """Basic synchronization with Odoo's standard email blacklist.

        Only global suppressions caused by a bounce/complaint/global
        opt-out reason are pushed to the standard blacklist. Purpose or
        mailing-list scoped suppressions must never reach it, otherwise
        opting out of one purpose would silently block every other one.
        """
        # newsletter_skip_blacklist_sync prevents a create-on-mail.blacklist
        # -> create-suppression-entry -> create-on-mail.blacklist loop with
        # the two-way sync in mail_blacklist.py.
        blacklist = self.env["mail.blacklist"].sudo().with_context(
            newsletter_skip_blacklist_sync=True
        )
        for rec in self:
            should_blacklist = (
                rec.active
                and rec.scope == "global"
                and (
                    rec.reason_id.category in GLOBAL_BLACKLIST_CATEGORIES
                    or rec.reason_id.code in GLOBAL_BLACKLIST_CODES
                )
            )
            if should_blacklist and rec.email_normalized:
                blacklist._add(rec.email_normalized)
            elif not rec.active and rec.email_normalized:
                blacklist._remove(rec.email_normalized)

    @api.constrains("scope", "brand_id", "purpose_id", "mailing_list_id", "campaign_mailing_id")
    def _check_scope(self):
        for rec in self:
            if rec.scope == "brand" and not rec.brand_id:
                raise ValidationError(
                    _("Brand is required for brand-scoped suppression.")
                )

            if rec.scope == "purpose" and not rec.purpose_id:
                raise ValidationError(
                    _("Consent Purpose is required for purpose suppression.")
                )

            if rec.scope == "mailing_list" and not rec.mailing_list_id:
                raise ValidationError(
                    _("Mailing List is required for mailing-list suppression.")
                )

            if rec.scope == "campaign" and not rec.campaign_mailing_id:
                raise ValidationError(
                    _("Campaign is required for campaign-scoped suppression.")
                )

    @api.constrains("partner_id", "identity_state")
    def _check_partner_required_while_identified(self):
        for rec in self:
            if rec.identity_state == "identified" and not rec.partner_id:
                raise ValidationError(
                    _("An identified suppression entry must reference a contact.")
                )

    def pseudonymize(self, reference=False):
        """Removes the direct identity link (partner_id, plain email) while
        keeping the HMAC token, scope, and reason intact - the suppression
        keeps blocking a matching email even though the record no longer
        names who it belongs to (R6-BR-06, R6-BR-11).
        """
        for rec in self:
            if rec.identity_state != "identified":
                continue
            rec.write(
                {
                    "partner_id": False,
                    "email_normalized": False,
                    "identity_state": "pseudonymized",
                    "pseudonymized_at": fields.Datetime.now(),
                    "pseudonymized_by_id": self.env.user.id,
                    "pseudonymization_reference": reference,
                }
            )
