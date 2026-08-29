from odoo import fields, models


class NewsletterRetentionMixin(models.AbstractModel):
    """Adds the standard retention fields (R6 section 8) to a model.
    Deliberately fields-only - retain_until calculation, expiry
    evaluation, and execution all live in retention_service.py so the
    logic isn't scattered across every model that carries these fields.
    """

    _name = "newsletter.retention.mixin"
    _description = "Newsletter Retention Fields Mixin"

    retention_policy_id = fields.Many2one(
        "newsletter.retention.policy", index=True, ondelete="set null"
    )
    retention_start_at = fields.Datetime()
    retain_until = fields.Datetime(index=True)
    retention_state = fields.Selection(
        [
            ("active", "Active"),
            ("approaching_expiry", "Approaching Expiry"),
            ("expired", "Expired"),
            ("on_hold", "On Legal Hold"),
            ("pseudonymized", "Pseudonymized"),
            ("purged", "Purged"),
        ],
        default="active",
    )
    legal_hold = fields.Boolean(default=False, index=True)
    retention_basis = fields.Selection(
        [
            ("active_service", "Active Service"),
            ("consent_evidence", "Consent Evidence"),
            ("opt_out_enforcement", "Opt-Out Enforcement"),
            ("regulatory_audit", "Regulatory Audit"),
            ("legal_hold", "Legal Hold"),
            ("security_investigation", "Security Investigation"),
            ("campaign_audit", "Campaign Audit"),
        ],
    )
