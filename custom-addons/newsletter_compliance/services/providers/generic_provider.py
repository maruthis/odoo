"""Reference provider adapter for generic/SMTP-based integrations.

Also doubles as the adapter used by tests, since we don't have real SES/
SendGrid/Mailgun credentials in this environment. A real SES/SendGrid/
Mailgun adapter would subclass NewsletterProviderAdapter the same way,
translating that provider's own signature scheme and payload shape into
the same canonical event - the rest of the pipeline never changes.

Authentication: HMAC-SHA256 over the raw request body, using a shared
secret stored in ir.config_parameter, sent as:

    X-Newsletter-Signature: sha256=<hex digest>
"""
import hashlib
import hmac
import json

from .base_provider import CanonicalDeliveryEvent, NewsletterProviderAdapter

CONFIG_PARAM_SECRET = "newsletter_compliance.generic_provider_secret"

_BOUNCE_TYPE_TO_CLASSIFICATION = {
    "permanent": "hard",
    "transient": "soft",
}


class GenericProviderAdapter(NewsletterProviderAdapter):
    provider_code = "generic"

    def __init__(self, env):
        self.env = env

    def _get_secret(self):
        return self.env["ir.config_parameter"].sudo().get_param(CONFIG_PARAM_SECRET)

    def validate_webhook(self, headers, body):
        secret = self._get_secret()
        if not secret:
            # No secret configured means the endpoint has not been set up
            # for this deployment - fail closed, never accept unauthenticated.
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
