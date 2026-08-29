import datetime
import hashlib
import json
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

# Bounce-type canonical events resolve to one of these via the adapter's
# classify_bounce(); "unknown" deliberately never auto-suppresses (R5
# section 29 - conservative classification is safer than wrongly
# suppressing a valid recipient).
_BOUNCE_EVENT_TYPES = {"soft_bounce", "hard_bounce"}


class NewsletterProviderEvent(models.Model):
    _name = "newsletter.provider.event"
    _inherit = ["newsletter.retention.mixin"]
    _description = "Newsletter Provider Delivery Event (raw inbound)"
    _order = "received_at desc, id desc"
    _rec_name = "reference"

    reference = fields.Char(readonly=True, copy=False, default="New")

    provider = fields.Char(required=True, index=True)
    provider_event_id = fields.Char(required=True, index=True)
    provider_message_id = fields.Char(index=True)

    received_at = fields.Datetime(default=fields.Datetime.now, required=True)
    event_timestamp = fields.Datetime()

    canonical_event_type = fields.Char()
    canonical_email = fields.Char(index=True)
    bounce_type = fields.Char()
    bounce_subtype = fields.Char()
    smtp_status = fields.Char()
    diagnostic_code = fields.Char()

    raw_payload = fields.Text(groups="newsletter_compliance.group_newsletter_compliance_admin")
    payload_hash = fields.Char(readonly=True)

    processing_state = fields.Selection(
        [
            ("received", "Received"),
            ("validated", "Validated"),
            ("processing", "Processing"),
            ("processed", "Processed"),
            ("unmatched", "Unmatched"),
            ("retry_pending", "Retry Pending"),
            ("failed", "Failed"),
            ("ignored_duplicate", "Ignored (Duplicate)"),
        ],
        default="received",
        required=True,
        index=True,
    )
    processing_attempts = fields.Integer(default=0)
    next_retry_at = fields.Datetime()
    error_message = fields.Text()

    send_event_id = fields.Many2one("newsletter.send.event", readonly=True, ondelete="set null")
    campaign_run_id = fields.Many2one(
        "newsletter.campaign.run", readonly=True, index=True, ondelete="set null"
    )
    eligibility_id = fields.Many2one(
        "newsletter.recipient.eligibility", readonly=True, ondelete="set null"
    )

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _provider_event_unique = models.Constraint(
        "unique(provider, provider_event_id)",
        "This provider event has already been received (idempotency guard).",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "New") == "New":
                vals["reference"] = (
                    self.env["ir.sequence"].next_by_code("newsletter.provider.event") or "New"
                )
            if vals.get("raw_payload") and not vals.get("payload_hash"):
                vals["payload_hash"] = hashlib.sha256(
                    vals["raw_payload"].encode("utf-8")
                ).hexdigest()
        return super().create(vals_list)

    @api.model
    def _fallback_event_id(self, provider, provider_message_id, event_type, timestamp, email):
        payload = "|".join(
            [provider, provider_message_id or "", event_type, timestamp or "", email or ""]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @api.model
    def _parse_event_timestamp(self, value):
        if not value:
            return fields.Datetime.now()
        if isinstance(value, str):
            # Canonical events carry ISO 8601 timestamps ("...T..."),
            # which Python's fromisoformat handles directly - Odoo's
            # Datetime field otherwise expects a plain datetime object or
            # a space-separated string, not "T"-separated ISO text.
            try:
                parsed = datetime.datetime.fromisoformat(value)
            except ValueError:
                return fields.Datetime.now()
            if parsed.tzinfo is not None:
                # Real providers (e.g. AWS SNS/SES) send a "Z"-suffixed,
                # timezone-aware timestamp - Odoo's Datetime field only
                # accepts a naive one, so normalize to naive UTC here
                # rather than letting every such event fail ingestion.
                parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return parsed
        return value

    @api.model
    def ingest(self, provider, canonical_event):
        """Persist one canonical event as a provider_event row. Idempotent:
        a duplicate (provider, provider_event_id) returns the existing
        record instead of raising, so the webhook controller can always
        return 200 without special-casing retries.
        """
        provider_event_id = canonical_event.provider_event_id or self._fallback_event_id(
            provider,
            canonical_event.provider_message_id,
            canonical_event.event_type,
            canonical_event.event_timestamp,
            canonical_event.email,
        )

        existing = self.sudo().search(
            [("provider", "=", provider), ("provider_event_id", "=", provider_event_id)], limit=1
        )
        if existing:
            return existing, False

        record = self.sudo().create(
            {
                "provider": provider,
                "provider_event_id": provider_event_id,
                "provider_message_id": canonical_event.provider_message_id,
                "event_timestamp": self._parse_event_timestamp(canonical_event.event_timestamp),
                "canonical_event_type": canonical_event.event_type,
                "canonical_email": (canonical_event.email or "").strip().lower(),
                "bounce_type": canonical_event.bounce_type,
                "bounce_subtype": canonical_event.bounce_subtype,
                "smtp_status": canonical_event.smtp_status,
                "diagnostic_code": canonical_event.diagnostic_code,
                "raw_payload": json.dumps(canonical_event.raw_payload, default=str),
            }
        )
        return record, True

    def _find_correlated_eligibility(self):
        self.ensure_one()
        if not self.provider_message_id:
            return self.env["newsletter.recipient.eligibility"]
        return self.env["newsletter.recipient.eligibility"].sudo().search(
            [("provider_message_id", "=", self.provider_message_id)], limit=1
        )

    def process_event(self):
        """Pipeline: correlate -> classify -> canonical send event ->
        delivery state -> reputation/suppression -> outcome -> alerts.
        Never raises past this method for routine failures - retries via
        the cron with exponential backoff, and never discards the raw
        event even after exhausting retries (R5-BR-18/19).
        """
        self.ensure_one()

        if self.processing_state == "processed":
            return

        try:
            self._process_event_body()
        except Exception as exc:  # noqa: BLE001
            self._handle_processing_failure(exc)

    def _process_event_body(self):
        from ..services import reputation_bridge

        self.write({"processing_state": "processing"})

        eligibility = self._find_correlated_eligibility()

        if not eligibility:
            self.write({"processing_state": "unmatched"})
            return

        run = eligibility.campaign_run_id
        mailing = eligibility.mailing_id

        # Idempotency at the business-event layer too: the DB constraint
        # on (source, provider_event_id) on newsletter.send.event means a
        # duplicate provider callback can never produce two business
        # events even if this method were somehow invoked twice for the
        # same provider_event.
        send_event = self.env["newsletter.send.event"].sudo().create(
            {
                "campaign_run_id": run.id,
                "mailing_id": mailing.id,
                "eligibility_id": eligibility.id,
                "partner_id": eligibility.partner_id.id,
                "mailing_contact_id": eligibility.mailing_contact_id.id,
                "email_normalized": eligibility.email_normalized,
                "event_type": self.canonical_event_type,
                "provider_message_id": self.provider_message_id,
                "provider_event_id": self.provider_event_id,
                "correlation_id": run._correlation_id(eligibility) if run else False,
                "source": "provider",
                "company_id": self.company_id.id,
            }
        )

        outcome = run.sudo().current_outcome_id if run else False
        bounce_classification = None

        if self.canonical_event_type == "delivered":
            eligibility.sudo().write({"delivery_state": "delivered"})
            reputation_bridge.apply_delivered(self.env, eligibility, self.event_timestamp)

        elif self.canonical_event_type == "delivery_delayed":
            eligibility.sudo().write({"delivery_state": "delayed"})

        elif self.canonical_event_type in _BOUNCE_EVENT_TYPES or self.canonical_event_type == "unknown":
            adapter = self._get_adapter()
            bounce_classification = (
                adapter.classify_bounce(self._to_canonical_event())
                if adapter
                else "unknown"
            )
            if self.canonical_event_type == "hard_bounce":
                bounce_classification = "hard"
            elif self.canonical_event_type == "soft_bounce" and bounce_classification == "unknown":
                bounce_classification = "soft"

            eligibility.sudo().write(
                {
                    "delivery_state": "hard_bounce" if bounce_classification == "hard" else (
                        "soft_bounce" if bounce_classification == "soft" else "unknown"
                    )
                }
            )
            reputation_bridge.apply_bounce(
                self.env, eligibility, bounce_classification, self.event_timestamp, send_event
            )

        elif self.canonical_event_type == "complaint":
            eligibility.sudo().write({"delivery_state": "complaint"})
            reputation_bridge.apply_complaint(self.env, eligibility, self.event_timestamp, send_event)

        elif self.canonical_event_type == "unsubscribe":
            reputation_bridge.apply_unsubscribe(self.env, eligibility, send_event)

        if outcome:
            if outcome.finalized:
                outcome.record_late_adjustment(
                    self.canonical_event_type, provider_event_id=self.provider_event_id
                )
            else:
                if self.canonical_event_type in ("soft_bounce", "hard_bounce", "unknown") and self.canonical_event_type != "delivered":
                    outcome._apply_bounce_count(bounce_classification or "unknown")
                else:
                    outcome._apply_event_count(self.canonical_event_type)
                reputation_bridge.evaluate_run_alerts(self.env, run)

        self.write(
            {
                "processing_state": "processed",
                "send_event_id": send_event.id,
                "campaign_run_id": run.id if run else False,
                "eligibility_id": eligibility.id,
            }
        )

    def _get_adapter(self):
        from ..services.providers import registry

        return registry.get_provider_adapter(self.env, self.provider)

    def _to_canonical_event(self):
        from ..services.providers.base_provider import CanonicalDeliveryEvent

        return CanonicalDeliveryEvent(
            provider=self.provider,
            provider_event_id=self.provider_event_id,
            provider_message_id=self.provider_message_id,
            event_type=self.canonical_event_type,
            event_timestamp=self.event_timestamp.isoformat() if self.event_timestamp else "",
            email=self.canonical_email,
            bounce_type=self.bounce_type,
            bounce_subtype=self.bounce_subtype,
            smtp_status=self.smtp_status,
            diagnostic_code=self.diagnostic_code,
            raw_payload=json.loads(self.raw_payload) if self.raw_payload else {},
        )

    def _handle_processing_failure(self, exc):
        from ..services import config_service, retry_service

        self.ensure_one()
        attempts = self.processing_attempts + 1
        max_attempts = config_service.get_event_processing_retry_limit(self.env)

        _logger.exception(
            "Provider event processing failed: reference=%s provider=%s event_id=%s",
            self.reference,
            self.provider,
            self.provider_event_id,
        )

        if attempts >= max_attempts:
            self.write(
                {
                    "processing_state": "failed",
                    "processing_attempts": attempts,
                    "error_message": str(exc),
                }
            )
            return

        delay = retry_service.calculate_next_retry_delay(attempts)

        self.write(
            {
                "processing_state": "retry_pending",
                "processing_attempts": attempts,
                "next_retry_at": fields.Datetime.now() + datetime.timedelta(seconds=delay),
                "error_message": str(exc),
            }
        )

    def purge_payload(self):
        """R6 section 28: once the canonical send event exists and the raw
        payload's own retention has expired, drop the payload while
        keeping the provider event, payload_hash, and canonical fields -
        auditability survives, the extra PII in the raw payload doesn't.
        """
        for record in self:
            record.write({"raw_payload": False, "retention_state": "purged"})

    @api.model
    def _cron_process_provider_events(self):
        events = self.search(
            [
                ("processing_state", "in", ["received", "validated", "retry_pending"]),
                "|",
                ("next_retry_at", "=", False),
                ("next_retry_at", "<=", fields.Datetime.now()),
            ],
            limit=200,
        )
        for event in events:
            try:
                event.process_event()
                self.env.cr.commit()
            except Exception:
                self.env.cr.rollback()
                _logger.exception(
                    "Unrecoverable error processing provider event %s", event.reference
                )
