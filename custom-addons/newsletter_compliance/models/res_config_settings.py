from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    newsletter_soft_bounce_threshold = fields.Integer(
        string="Soft Bounce Threshold",
        config_parameter="newsletter_compliance.soft_bounce_threshold",
        default=3,
    )
    newsletter_soft_bounce_window_days = fields.Integer(
        string="Soft Bounce Window (days)",
        config_parameter="newsletter_compliance.soft_bounce_window_days",
        default=90,
    )
    newsletter_bounce_warning_rate = fields.Float(
        string="Bounce Warning Rate",
        config_parameter="newsletter_compliance.bounce_warning_rate",
        default=0.02,
    )
    newsletter_bounce_critical_rate = fields.Float(
        string="Bounce Critical Rate",
        config_parameter="newsletter_compliance.bounce_critical_rate",
        default=0.05,
    )
    newsletter_complaint_warning_rate = fields.Float(
        string="Complaint Warning Rate",
        config_parameter="newsletter_compliance.complaint_warning_rate",
        default=0.0005,
    )
    newsletter_complaint_critical_rate = fields.Float(
        string="Complaint Critical Rate",
        config_parameter="newsletter_compliance.complaint_critical_rate",
        default=0.001,
    )
    newsletter_unsubscribe_warning_rate = fields.Float(
        string="Unsubscribe Warning Rate",
        config_parameter="newsletter_compliance.unsubscribe_warning_rate",
        default=0.02,
    )
    newsletter_auto_suspend_on_critical = fields.Boolean(
        string="Auto-Suspend on Critical Threshold",
        config_parameter="newsletter_compliance.auto_suspend_on_critical",
        default=True,
    )
    newsletter_outcome_finalization_window_hours = fields.Integer(
        string="Outcome Finalization Window (hours)",
        config_parameter="newsletter_compliance.outcome_finalization_window_hours",
        default=72,
    )
    newsletter_event_processing_retry_limit = fields.Integer(
        string="Event Processing Retry Limit",
        config_parameter="newsletter_compliance.event_processing_retry_limit",
        default=5,
    )
    newsletter_generic_provider_secret = fields.Char(
        string="Generic Provider Webhook Secret",
        config_parameter="newsletter_compliance.generic_provider_secret",
    )
    newsletter_smtp_bounce_relay_secret = fields.Char(
        string="SMTP Bounce Relay Secret",
        config_parameter="newsletter_compliance.smtp_bounce_relay_secret",
    )
    newsletter_ses_sns_topic_arn = fields.Char(
        string="SES SNS Topic ARN",
        config_parameter="newsletter_compliance.ses_sns_topic_arn",
    )
    newsletter_sendgrid_webhook_public_key = fields.Char(
        string="SendGrid Webhook Public Key",
        config_parameter="newsletter_compliance.sendgrid_webhook_public_key",
    )
    newsletter_mailgun_signing_key = fields.Char(
        string="Mailgun Webhook Signing Key",
        config_parameter="newsletter_compliance.mailgun_signing_key",
    )

    # -- Preflight -----------------------------------------------------
    newsletter_minimum_eligible_recipient_count = fields.Integer(
        string="Minimum Eligible Recipients",
        config_parameter="newsletter_compliance.minimum_eligible_recipient_count",
        default=1,
    )
    newsletter_max_preflight_age_minutes = fields.Integer(
        string="Maximum Preflight Age (minutes)",
        config_parameter="newsletter_compliance.max_preflight_age_minutes",
        default=1440,
    )

    # -- Dispatch --------------------------------------------------------
    newsletter_dispatch_batch_size = fields.Integer(
        string="Dispatch Batch Size",
        config_parameter="newsletter_compliance.dispatch_batch_size",
        default=500,
    )
    newsletter_maximum_retry_count = fields.Integer(
        string="Maximum Retry Count",
        config_parameter="newsletter_compliance.maximum_retry_count",
        default=5,
    )
    newsletter_base_retry_delay_seconds = fields.Integer(
        string="Base Retry Delay (seconds)",
        config_parameter="newsletter_compliance.base_retry_delay_seconds",
        default=60,
    )
    newsletter_maximum_retry_delay_seconds = fields.Integer(
        string="Maximum Retry Delay (seconds)",
        config_parameter="newsletter_compliance.maximum_retry_delay_seconds",
        default=3600,
    )

    # -- Retention ---------------------------------------------------------
    newsletter_retention_batch_size = fields.Integer(
        string="Retention Batch Size",
        config_parameter="newsletter_compliance.retention_batch_size",
        default=1000,
    )
    newsletter_retention_dry_run_default = fields.Boolean(
        string="New Retention Policies Default to Dry-Run",
        config_parameter="newsletter_compliance.retention_dry_run_default",
        default=True,
    )
    newsletter_audit_export_expiry_days = fields.Integer(
        string="Audit Export Availability (days)",
        config_parameter="newsletter_compliance.audit_export_expiry_days",
        default=7,
    )
