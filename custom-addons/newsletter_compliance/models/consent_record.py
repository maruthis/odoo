from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

PROTECTED_EVIDENCE_FIELDS = {
    "partner_id",
    "email_normalized",
    "purpose_id",
    "given_at",
    "source",
    "channel",
    "privacy_notice_version",
    "consent_text",
    "evidence_attachment_id",
}

FINALIZED_STATES = {"active", "withdrawn", "expired", "superseded"}


class NewsletterConsentRecord(models.Model):
    _name = "newsletter.consent.record"
    _description = "Newsletter Consent Record"
    _inherit = ["mail.thread", "mail.activity.mixin", "newsletter.retention.mixin"]
    _order = "given_at desc, id desc"

    reference = fields.Char(
        readonly=True,
        copy=False,
        default="New",
        tracking=True,
    )

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        index=True,
        ondelete="restrict",
        tracking=True,
    )

    email = fields.Char(
        related="partner_id.email",
        readonly=True,
    )

    email_normalized = fields.Char(
        required=True,
        index=True,
        readonly=True,
    )

    purpose_id = fields.Many2one(
        "newsletter.consent.purpose",
        required=True,
        index=True,
        ondelete="restrict",
        tracking=True,
    )

    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("active", "Active"),
            ("withdrawn", "Withdrawn"),
            ("expired", "Expired"),
            ("invalidated", "Invalidated"),
            ("superseded", "Superseded"),
        ],
        default="pending",
        required=True,
        index=True,
        tracking=True,
    )

    given_at = fields.Datetime(tracking=True)
    expires_at = fields.Datetime(tracking=True)

    withdrawn_at = fields.Datetime(
        readonly=True,
        tracking=True,
    )

    source = fields.Selection(
        [
            ("website", "Website"),
            ("email", "Email"),
            ("paper", "Paper"),
            ("phone", "Phone"),
            ("in_person", "In Person"),
            ("crm", "CRM"),
            ("import", "Controlled Import"),
            ("api", "API"),
            ("manual", "Authorized Manual Entry"),
            ("other", "Other"),
        ],
        required=True,
        tracking=True,
    )

    channel = fields.Selection(
        [
            ("web", "Web"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("in_person", "In Person"),
            ("paper", "Paper"),
            ("system", "System"),
            ("other", "Other"),
        ],
        required=True,
        tracking=True,
    )

    privacy_notice_version = fields.Char(
        required=True,
        tracking=True,
    )

    source_reference = fields.Char()
    consent_text = fields.Text()

    evidence_attachment_id = fields.Many2one(
        "ir.attachment",
        ondelete="restrict",
    )

    withdrawal_reason = fields.Text(readonly=True)

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
        readonly=True,
    )

    supersedes_id = fields.Many2one(
        "newsletter.consent.record",
        string="Superseded Consent",
        readonly=True,
        ondelete="restrict",
    )

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    active = fields.Boolean(default=True)

    confirmation_token = fields.Char(
        readonly=True,
        copy=False,
        index=True,
        help="Double opt-in confirmation token. Set when a pending consent "
        "record is created via the public subscribe page; cleared once "
        "confirmed. Several purposes submitted in the same subscribe "
        "request share one token, so a single confirmation click confirms "
        "all of them.",
    )
    confirmation_requested_at = fields.Datetime(readonly=True)

    @api.model
    def _normalize_email(self, email):
        return (email or "").strip().lower()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            partner = self.env["res.partner"].browse(vals.get("partner_id"))

            vals["email_normalized"] = self._normalize_email(partner.email)

            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("newsletter.consent.record")
                    or "New"
                )

        return super().create(vals_list)

    def write(self, vals):
        finalized = self.filtered(lambda r: r.status in FINALIZED_STATES)

        if finalized and PROTECTED_EVIDENCE_FIELDS.intersection(vals):
            raise UserError(
                _(
                    "Finalized consent evidence cannot be changed. "
                    "Create a superseding consent record instead."
                )
            )

        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda r: r.status != "pending"):
            raise UserError(_("Finalized consent records cannot be deleted."))

        return super().unlink()

    @api.constrains("status", "given_at")
    def _check_active_consent_timestamp(self):
        for rec in self:
            if rec.status == "active" and not rec.given_at:
                raise ValidationError(
                    _("Active consent must have a consent timestamp.")
                )

    @api.constrains("given_at", "expires_at")
    def _check_expiry_date(self):
        for rec in self:
            if rec.given_at and rec.expires_at and rec.expires_at <= rec.given_at:
                raise ValidationError(_("Expiry must occur after consent was given."))

    @api.model
    def _cron_expire_consents(self):
        """Bulk Email blueprint §23 "Consent expiry": proactively stamps
        status=expired once expires_at passes, rather than leaving expiry
        as something only checked live at evaluation time. The eligibility
        engine and discovery service already treat an expired consent as
        not-currently-valid regardless of this cron running, so this only
        changes whether the stored status field itself reflects reality -
        not whether expired consent is ever honored.
        """
        expired = self.search(
            [
                ("status", "=", "active"),
                ("expires_at", "!=", False),
                ("expires_at", "<=", fields.Datetime.now()),
            ]
        )
        if expired:
            expired.write({"status": "expired"})
