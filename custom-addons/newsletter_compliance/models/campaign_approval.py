from odoo import fields, models


class NewsletterCampaignApproval(models.Model):
    _name = "newsletter.campaign.approval"
    _description = "Newsletter Campaign Approval History"
    _order = "mailing_id, approval_version, id"
    _rec_name = "mailing_id"

    mailing_id = fields.Many2one(
        "mailing.mailing",
        required=True,
        index=True,
        ondelete="cascade",
    )

    approval_version = fields.Integer(required=True)

    approval_type = fields.Selection(
        [
            ("content", "Content"),
            ("compliance", "Compliance"),
        ],
        required=True,
    )

    decision = fields.Selection(
        [
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("invalidated", "Invalidated"),
        ],
        required=True,
    )

    reviewer_id = fields.Many2one("res.users", required=True)
    reviewed_at = fields.Datetime(required=True, default=fields.Datetime.now)

    comments = fields.Text()

    content_hash = fields.Char()
    subject_snapshot = fields.Char()
    recipient_snapshot = fields.Text()

    consent_purpose_id = fields.Many2one(
        "newsletter.consent.purpose",
        ondelete="restrict",
    )

    brand_id = fields.Many2one(
        "newsletter.campaign.brand",
        ondelete="restrict",
    )

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
