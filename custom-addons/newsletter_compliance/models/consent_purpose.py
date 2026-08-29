from odoo import fields, models


class NewsletterConsentPurpose(models.Model):
    _name = "newsletter.consent.purpose"
    _description = "Newsletter Consent Purpose"
    _order = "name"

    name = fields.Char(required=True, index=True)
    code = fields.Char(required=True, index=True)

    description = fields.Text()

    requires_explicit_consent = fields.Boolean(
        string="Explicit Consent Required",
        default=True,
        required=True,
    )

    privacy_notice_version = fields.Char(
        string="Privacy Notice Version",
        required=True,
    )

    retention_days = fields.Integer(
        default=2555,
        help="Default retention period for consent evidence.",
    )

    public_subscribe = fields.Boolean(
        string="Offer on Public Subscribe Page",
        default=True,
        help="Whether this purpose appears as a selectable checkbox on the "
        "public subscribe page - internal-only purposes can be excluded.",
    )

    active = fields.Boolean(default=True)

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _code_company_unique = models.Constraint(
        "unique(code, company_id)",
        "Consent purpose code must be unique per company.",
    )
