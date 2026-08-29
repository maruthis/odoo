"""SendGrid Event Webhook adapter.

SendGrid signs the raw request body with Ed25519 ("signed event webhook"):
https://www.twilio.com/docs/sendgrid/for-developers/tracking-events/getting-started-event-webhook-security-features
The verification key is the base64-encoded public key SendGrid shows when
signed webhooks are enabled, stored in ir.config_parameter. The signature
covers ``timestamp + body`` exactly, taken from the
``X-Twilio-Email-Event-Webhook-Signature`` / ``-Timestamp`` headers.
"""
import base64
import json

from .base_provider import CanonicalDeliveryEvent, NewsletterProviderAdapter

CONFIG_PARAM_PUBLIC_KEY = "newsletter_compliance.sendgrid_webhook_public_key"

_SIGNATURE_HEADER = "X-Twilio-Email-Event-Webhook-Signature"
_TIMESTAMP_HEADER = "X-Twilio-Email-Event-Webhook-Timestamp"

# https://docs.sendgrid.com/for-developers/tracking-events/event
_EVENT_TYPE_MAP = {
    "delivered": "delivered",
    "processed": "accepted",
    "deferred": "delivery_delayed",
    "bounce": "hard_bounce",  # refined via "type" field below
    "dropped": "provider_dropped",
    "spamreport": "complaint",
    "unsubscribe": "unsubscribe",
    "group_unsubscribe": "unsubscribe",
}


class SendGridProviderAdapter(NewsletterProviderAdapter):
    provider_code = "sendgrid"

    def __init__(self, env):
        self.env = env

    def _get_public_key(self):
        return self.env["ir.config_parameter"].sudo().get_param(CONFIG_PARAM_PUBLIC_KEY)

    def validate_webhook(self, headers, body):
        public_key_b64 = self._get_public_key()
        if not public_key_b64:
            return False

        signature_b64 = headers.get(_SIGNATURE_HEADER)
        timestamp = headers.get(_TIMESTAMP_HEADER)
        if not signature_b64 or not timestamp:
            return False

        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
            signed_payload = timestamp.encode("utf-8") + (
                body if isinstance(body, bytes) else body.encode("utf-8")
            )
            public_key.verify(base64.b64decode(signature_b64), signed_payload)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    def normalize_event(self, payload):
        if isinstance(payload, (bytes, str)):
            payload = json.loads(payload)

        events = payload if isinstance(payload, list) else [payload]
        canonical_events = []
        for raw in events:
            sg_event = raw.get("event", "unknown")
            event_type = _EVENT_TYPE_MAP.get(sg_event, "unknown")
            bounce_type = None
            if sg_event == "bounce":
                # "type" is "bounce" (hard) or "blocked" (soft) per SendGrid docs
                bounce_type = "permanent" if raw.get("type") == "bounce" else "transient"
                event_type = "hard_bounce" if bounce_type == "permanent" else "soft_bounce"

            timestamp = raw.get("timestamp")
            canonical_events.append(
                CanonicalDeliveryEvent(
                    provider=self.provider_code,
                    provider_event_id=raw.get("sg_event_id", ""),
                    provider_message_id=raw.get("sg_message_id"),
                    event_type=event_type,
                    event_timestamp=self._format_timestamp(timestamp),
                    email=raw.get("email"),
                    bounce_type=bounce_type,
                    smtp_status=str(raw.get("status") or "") or None,
                    diagnostic_code=raw.get("reason"),
                    raw_payload=raw,
                )
            )
        return canonical_events

    @staticmethod
    def _format_timestamp(value):
        if not value:
            return ""
        import datetime

        return datetime.datetime.fromtimestamp(float(value), tz=datetime.timezone.utc).isoformat()

    def classify_bounce(self, canonical_event):
        if canonical_event.bounce_type == "permanent":
            return "hard"
        if canonical_event.bounce_type == "transient":
            return "soft"
        return "unknown"
