"""Adapter for self-hosted/plain-SMTP delivery.

Plain SMTP has no native webhook format - bounces and complaints arrive as
non-delivery report (NDR) emails to a return-path mailbox, not as
structured HTTP callbacks. This adapter therefore expects an external NDR
parser (a fetchmail/procmail job, or Odoo's own bounce-alias processing)
to translate those NDRs into the same canonical JSON shape the generic
adapter accepts, and to sign the request with its own HMAC secret so an
SMTP-only deployment doesn't have to share the webhook-facing providers'
secret.
"""
import hashlib
import hmac
import json

from .base_provider import CanonicalDeliveryEvent, NewsletterProviderAdapter

CONFIG_PARAM_SECRET = "newsletter_compliance.smtp_bounce_relay_secret"

_BOUNCE_TYPE_TO_CLASSIFICATION = {
    "permanent": "hard",
    "transient": "soft",
}


class SmtpProviderAdapter(NewsletterProviderAdapter):
    provider_code = "smtp"

    def __init__(self, env):
        self.env = env

    def _get_secret(self):
        return self.env["ir.config_parameter"].sudo().get_param(CONFIG_PARAM_SECRET)

    def validate_webhook(self, headers, body):
        secret = self._get_secret()
        if not secret:
            return False

        signature_header = headers.get("X-Newsletter-Signature", "")
        if not signature_header.startswith("sha256="):
            return False

        provided = signature_header.split("=", 1)[1]
        expected = hmac.new(
            secret.encode("utf-8"),
            body if isinstance(body, bytes) else body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(provided, expected)

    def normalize_event(self, payload):
        if isinstance(payload, (bytes, str)):
            payload = json.loads(payload)

        events = payload if isinstance(payload, list) else [payload]
        canonical_events = []
        for raw in events:
            canonical_events.append(
                CanonicalDeliveryEvent(
                    provider=self.provider_code,
                    provider_event_id=raw.get("provider_event_id") or "",
                    provider_message_id=raw.get("provider_message_id"),
                    event_type=raw.get("event_type", "unknown"),
                    event_timestamp=raw.get("event_timestamp") or "",
                    email=raw.get("email"),
                    bounce_type=raw.get("bounce_type"),
                    bounce_subtype=raw.get("bounce_subtype"),
                    smtp_status=raw.get("smtp_status"),
                    diagnostic_code=raw.get("diagnostic_code"),
                    raw_payload=raw,
                )
            )
        return canonical_events

    def classify_bounce(self, canonical_event):
        return _BOUNCE_TYPE_TO_CLASSIFICATION.get(canonical_event.bounce_type, "unknown")
