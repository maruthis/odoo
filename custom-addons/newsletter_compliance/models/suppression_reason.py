from odoo import fields, models


class NewsletterSuppressionReason(models.Model):
    _name = "newsletter.suppression.reason"
    _description = "Newsletter Suppression Reason"
    _order = "name"

    name = fields.Char(required=True, index=True)
    code = fields.Char(required=True, index=True)

    category = fields.Selection(
        [
            ("bounce", "Bounce"),
            ("complaint", "Complaint"),
            ("unsubscribe", "Unsubscribe"),
            ("compliance", "Compliance"),
        ],
        required=True,
    )

    default_scope = fields.Selection(
        [
            ("global", "Global"),
            ("brand", "Brand"),
            ("purpose", "Purpose"),
        ],
        required=True,
        default="global",
    )

    auto_suppress = fields.Boolean(
        string="Automatically Create Suppression",
        default=True,
    )

    allow_reinstatement = fields.Boolean(
        string="Allow Reinstatement",
        default=True,
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
        "Suppression reason code must be unique per company.",
    )
