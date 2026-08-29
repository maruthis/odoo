from odoo import fields, models

from ..services import config_service

DATA_CATEGORIES = [
    ("consent_evidence", "Consent Evidence"),
    ("consent_history", "Consent History"),
    ("suppression_history", "Suppression History"),
    ("recipient_eligibility", "Recipient Eligibility"),
    ("campaign_run", "Campaign Run"),
    ("send_event", "Send Event"),
    ("provider_raw_event", "Provider Raw Event"),
    ("campaign_archive", "Campaign Archive"),
    ("campaign_outcome", "Campaign Outcome"),
    ("recipient_reputation", "Recipient Reputation"),
    ("compliance_alert", "Compliance Alert"),
    ("approval_history", "Approval History"),
    ("audit_export", "Audit Export"),
]

# Maps each data category to the model it governs and which field on that
# model marks the moment its retention clock starts - kept in one place
# (retention_service.py) per R6 section 9, referenced from there.
RETENTION_TRIGGERS = [
    ("record_created", "Record Created"),
    ("consent_given", "Consent Given"),
    ("consent_withdrawn", "Consent Withdrawn"),
    ("campaign_completed", "Campaign Completed"),
    ("campaign_archived", "Campaign Archived"),
    ("last_delivery_event", "Last Delivery Event"),
    ("suppression_reinstated", "Suppression Reinstated"),
    ("outcome_finalized", "Outcome Finalized"),
    ("legal_hold_released", "Legal Hold Released"),
]


class NewsletterRetentionPolicy(models.Model):
    _name = "newsletter.retention.policy"
    _description = "Newsletter Retention Policy"
    _order = "data_category"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)

    data_category = fields.Selection(DATA_CATEGORIES, required=True, index=True)

    retention_period_days = fields.Integer(required=True)
    retention_trigger = fields.Selection(RETENTION_TRIGGERS, required=True, default="record_created")

    expiry_action = fields.Selection(
        [
            ("retain", "Retain"),
            ("review", "Manual Review"),
            ("pseudonymize", "Pseudonymize"),
            ("anonymize", "Anonymize"),
            ("purge_payload", "Remove Raw Payload"),
            ("delete", "Delete"),
        ],
        required=True,
        default="review",
    )

    legal_hold_allowed = fields.Boolean(default=True)
    pseudonymize_before_delete = fields.Boolean(default=True)
    minimum_evidence_fields = fields.Text(
        help="Free-text note of what must survive even after the expiry "
        "action runs (e.g. 'scope, reason, email_hash, effective_from')."
    )

    batch_size = fields.Integer(
        default=lambda self: config_service.get_retention_batch_size(self.env)
    )
    dry_run = fields.Boolean(
        default=lambda self: config_service.get_retention_dry_run_default(self.env),
        help="While enabled, the retention processor only previews the "
        "impact of this policy and never mutates data (R6 section 34).",
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
        "Retention policy code must be unique per company.",
    )

    def _cron_process_retention(self):
        from ..services import retention_service

        policies = self.search([("active", "=", True)]) if not self else self
        for policy in policies:
            retention_service.process_policy(self.env, policy)
