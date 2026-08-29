from odoo import api, fields, models, _

ALERT_TYPES = [
    ("bounce_threshold", "Bounce Threshold"),
    ("complaint_threshold", "Complaint Threshold"),
    ("unsubscribe_spike", "Unsubscribe Spike"),
    ("technical_failure_threshold", "Technical Failure Threshold"),
    ("provider_event_failure", "Provider Event Failure"),
    ("provider_event_backlog", "Provider Event Backlog"),
    ("unmatched_provider_events", "Unmatched Provider Events"),
    ("reputation_risk", "Reputation Risk"),
    ("archive_integrity_failure", "Archive Integrity Failure"),
    ("retention_failure", "Retention Processing Failure"),
    ("privacy_request_overdue", "Privacy Request Overdue"),
]

# Alert types that are scoped to a single campaign run - deduplication key
# is (campaign_run_id, alert_type). Operational alerts (backlog, unmatched)
# aren't run-scoped, so they dedupe on alert_type alone.
RUN_SCOPED_ALERT_TYPES = {
    "bounce_threshold",
    "complaint_threshold",
    "unsubscribe_spike",
    "technical_failure_threshold",
}


class NewsletterComplianceAlert(models.Model):
    _name = "newsletter.compliance.alert"
    _description = "Newsletter Compliance Alert"
    _order = "raised_at desc, id desc"
    _rec_name = "reference"

    reference = fields.Char(readonly=True, copy=False, default="New")

    alert_type = fields.Selection(ALERT_TYPES, required=True, index=True)
    severity = fields.Selection(
        [
            ("info", "Info"),
            ("warning", "Warning"),
            ("critical", "Critical"),
        ],
        required=True,
        default="warning",
        index=True,
    )

    campaign_run_id = fields.Many2one(
        "newsletter.campaign.run", index=True, ondelete="cascade"
    )
    provider = fields.Char()

    raised_at = fields.Datetime(default=fields.Datetime.now, required=True)
    metric_name = fields.Char()
    metric_value = fields.Float()
    threshold_value = fields.Float()

    status = fields.Selection(
        [
            ("open", "Open"),
            ("acknowledged", "Acknowledged"),
            ("resolved", "Resolved"),
        ],
        default="open",
        required=True,
        index=True,
    )

    assigned_to = fields.Many2one("res.users")
    acknowledged_at = fields.Datetime(readonly=True)
    acknowledged_by_id = fields.Many2one("res.users", readonly=True)
    resolved_at = fields.Datetime(readonly=True)
    resolved_by_id = fields.Many2one("res.users", readonly=True)
    resolution_notes = fields.Text()

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("newsletter.compliance.alert") or "New"
                )
        return super().create(vals_list)

    @api.model
    def _create_or_update_alert(
        self, alert_type, severity, metric_name, metric_value, threshold_value,
        campaign_run=None, provider=False,
    ):
        """Idempotent alert raising: one active (open/acknowledged) alert
        per (campaign_run, alert_type) - or per alert_type alone for
        non-run-scoped operational alerts. Refreshes the metric on the
        existing alert rather than spamming new ones.
        """
        domain = [("alert_type", "=", alert_type), ("status", "!=", "resolved")]
        if alert_type in RUN_SCOPED_ALERT_TYPES:
            domain.append(("campaign_run_id", "=", campaign_run.id if campaign_run else False))

        existing = self.sudo().search(domain, limit=1)
        if existing:
            existing.sudo().write(
                {
                    "metric_value": metric_value,
                    "severity": severity,
                }
            )
            return existing

        alert = self.sudo().create(
            {
                "alert_type": alert_type,
                "severity": severity,
                "campaign_run_id": campaign_run.id if campaign_run else False,
                "provider": provider,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "threshold_value": threshold_value,
            }
        )

        if campaign_run:
            operator_activity_user = campaign_run.execution_started_by_id or self.env.user
            campaign_run.mailing_id.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_(
                    "Compliance alert: %(alert_type)s (value %(value)s)",
                    alert_type=alert_type,
                    value=round(metric_value, 4),
                ),
                user_id=operator_activity_user.id,
            )
            campaign_run.mailing_id.message_post(
                body=_(
                    "Compliance alert raised: %(alert_type)s. %(metric)s = %(value).4f "
                    "(threshold %(threshold).4f).",
                    alert_type=alert_type,
                    metric=metric_name,
                    value=metric_value,
                    threshold=threshold_value,
                )
            )

        return alert

    def action_acknowledge(self):
        for alert in self:
            if alert.status == "open":
                alert.write(
                    {
                        "status": "acknowledged",
                        "acknowledged_at": fields.Datetime.now(),
                        "acknowledged_by_id": self.env.user.id,
                    }
                )

    def action_resolve(self, notes=False):
        for alert in self:
            alert.write(
                {
                    "status": "resolved",
                    "resolved_at": fields.Datetime.now(),
                    "resolved_by_id": self.env.user.id,
                    "resolution_notes": notes,
                }
            )
