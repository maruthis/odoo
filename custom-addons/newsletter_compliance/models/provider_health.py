from odoo import api, fields, models

BACKLOG_WARNING_MINUTES = 10
BACKLOG_WARNING_COUNT = 100
UNMATCHED_WARNING_COUNT = 20


class NewsletterProviderHealth(models.Model):
    _name = "newsletter.provider.health"
    _description = "Newsletter Provider Health"
    _order = "provider"
    _rec_name = "provider"

    provider = fields.Char(required=True, index=True)

    last_event_received_at = fields.Datetime(readonly=True)
    last_successful_send_at = fields.Datetime(readonly=True)

    webhook_backlog_count = fields.Integer(readonly=True, default=0)
    event_processing_failures = fields.Integer(readonly=True, default=0)
    unmatched_events_count = fields.Integer(readonly=True, default=0)
    avg_callback_latency_seconds = fields.Float(readonly=True, default=0.0)

    state = fields.Selection(
        [
            ("healthy", "Healthy"),
            ("degraded", "Degraded"),
            ("unavailable", "Unavailable"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
        readonly=True,
    )

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _provider_company_unique = models.Constraint(
        "unique(provider, company_id)",
        "Only one health record per provider per company.",
    )

    @api.model
    def _get_or_create(self, provider):
        record = self.sudo().search([("provider", "=", provider)], limit=1)
        if not record:
            record = self.sudo().create({"provider": provider})
        return record

    @api.model
    def _cron_update_provider_health(self):
        import datetime

        ProviderEvent = self.env["newsletter.provider.event"]
        providers = ProviderEvent.sudo().search([]).mapped("provider")

        for provider in set(providers) or {"generic"}:
            health = self._get_or_create(provider)

            events = ProviderEvent.sudo().search([("provider", "=", provider)])
            backlog = events.filtered(
                lambda e: e.processing_state in ("received", "validated", "retry_pending")
                and e.received_at
                and e.received_at < fields.Datetime.now() - datetime.timedelta(
                    minutes=BACKLOG_WARNING_MINUTES
                )
            )
            unmatched = events.filtered(lambda e: e.processing_state == "unmatched")
            failures = events.filtered(lambda e: e.processing_state == "failed")
            latest = events.sorted("received_at", reverse=True)[:1]

            if latest:
                state = "healthy"
            elif not events:
                state = "unknown"
            else:
                state = "healthy"

            if len(backlog) >= BACKLOG_WARNING_COUNT:
                state = "degraded"
                self.env["newsletter.compliance.alert"]._create_or_update_alert(
                    "provider_event_backlog",
                    "warning",
                    "backlog_count",
                    len(backlog),
                    BACKLOG_WARNING_COUNT,
                    provider=provider,
                )

            if len(unmatched) >= UNMATCHED_WARNING_COUNT:
                self.env["newsletter.compliance.alert"]._create_or_update_alert(
                    "unmatched_provider_events",
                    "warning",
                    "unmatched_count",
                    len(unmatched),
                    UNMATCHED_WARNING_COUNT,
                    provider=provider,
                )

            health.write(
                {
                    "last_event_received_at": latest.received_at if latest else health.last_event_received_at,
                    "webhook_backlog_count": len(backlog),
                    "event_processing_failures": len(failures),
                    "unmatched_events_count": len(unmatched),
                    "state": state,
                }
            )
