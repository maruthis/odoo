from odoo import fields, models


class NewsletterCampaignBrand(models.Model):
    _name = "newsletter.campaign.brand"
    _description = "Newsletter Campaign Brand / Business Domain"
    _order = "name"

    name = fields.Char(required=True, index=True)
    code = fields.Char(required=True, index=True)

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    email_from = fields.Char(string="From Address")
    reply_to = fields.Char(string="Reply-To")

    physical_address = fields.Text(
        string="Physical Mailing Address",
        help="Required by regulation on every commercial/marketing email "
        "sent under this brand.",
    )

    website_url = fields.Char(string="Website URL")

    default_consent_purpose_id = fields.Many2one(
        "newsletter.consent.purpose",
        string="Default Consent Purpose",
        ondelete="restrict",
    )

    active = fields.Boolean(default=True)

    _code_company_unique = models.Constraint(
        "unique(code, company_id)",
        "Brand code must be unique per company.",
    )
