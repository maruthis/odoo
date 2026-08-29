"""Mailgun webhook adapter.

Mailgun signs each webhook with HMAC-SHA256(signing_key, timestamp + token)
delivered inside the payload itself under payload["signature"] (rather
than as a header) - see
https://documentation.mailgun.com/en/latest/user_manual.html#webhooks-1.
The signing key is the account's webhook signing key, stored in
ir.config_parameter, never the general API key.
"""
import datetime
import hashlib
import hmac
import json

from .base_provider import CanonicalDeliveryEvent, NewsletterProviderAdapter

CONFIG_PARAM_SIGNING_KEY = "newsletter_compliance.mailgun_signing_key"

# https://documentation.mailgun.com/en/latest/api-events.html#event-structure
_EVENT_TYPE_MAP = {
    "delivered": "delivered",
    "accepted": "accepted",
    "failed": "hard_bounce",  # refined to soft/hard below via severity
    "complained": "complaint",
    "unsubscribed": "unsubscribe",
    "rejected": "provider_rejected",
}


class MailgunProviderAdapter(NewsletterProviderAdapter):
    provider_code = "mailgun"

    def __init__(self, env):
        self.env = env

    def _get_signing_key(self):
        return self.env["ir.config_parameter"].sudo().get_param(CONFIG_PARAM_SIGNING_KEY)

    def validate_webhook(self, headers, body):
        signing_key = self._get_signing_key()
        if not signing_key:
            return False

        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            return False

        signature_block = payload.get("signature") or {}
        timestamp = signature_block.get("timestamp", "")
        token = signature_block.get("token", "")
        provided = signature_block.get("signature", "")
        if not (timestamp and token and provided):
            return False

        expected = hmac.new(
            signing_key.encode("utf-8"),
            f"{timestamp}{token}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(provided, expected)

    def normalize_event(self, payload):
        if isinstance(payload, (bytes, str)):
            payload = json.loads(payload)

        event_data = payload.get("event-data", payload)
        severity = event_data.get("severity")  # "permanent" | "temporary" (failed events)
        mailgun_event = event_data.get("event", "unknown")

        event_type = _EVENT_TYPE_MAP.get(mailgun_event, "unknown")
        bounce_type = None
        if mailgun_event == "failed":
            bounce_type = "permanent" if severity == "permanent" else "transient"
            event_type = "hard_bounce" if bounce_type == "permanent" else "soft_bounce"

        message = event_data.get("message", {}) or {}
        recipient = event_data.get("recipient")
        delivery_status = event_data.get("delivery-status", {}) or {}

        raw_timestamp = event_data.get("timestamp")
        event_timestamp = (
            datetime.datetime.fromtimestamp(
                float(raw_timestamp), tz=datetime.timezone.utc
            ).isoformat()
            if raw_timestamp
            else ""
        )

        return [
            CanonicalDeliveryEvent(
                provider=self.provider_code,
                provider_event_id=event_data.get("id", ""),
                provider_message_id=(message.get("headers") or {}).get("message-id"),
                event_type=event_type,
                event_timestamp=event_timestamp,
                email=recipient,
                bounce_type=bounce_type,
                smtp_status=str(delivery_status.get("code") or "") or None,
                diagnostic_code=delivery_status.get("description"),
                raw_payload=event_data,
            )
        ]

    def classify_bounce(self, canonical_event):
        if canonical_event.bounce_type == "permanent":
            return "hard"
        if canonical_event.bounce_type == "transient":
            return "soft"
        return "unknown"
