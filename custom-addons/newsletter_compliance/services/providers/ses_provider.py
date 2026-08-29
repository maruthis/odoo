"""AWS SES adapter, delivered via an SNS HTTP(S) subscription.

SES itself doesn't call webhooks directly - bounce/complaint/delivery
notifications are published to an SNS topic, which SNS then POSTs to this
endpoint as its own envelope (Type/MessageId/TopicArn/Message/Signature/
SigningCertURL/...), with the actual SES event JSON nested inside the
``Message`` string. See:
https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html
https://docs.aws.amazon.com/ses/latest/dg/notification-contents.html

Verification fetches the signing certificate named by ``SigningCertURL``
and checks the RSA signature over the canonical string SNS defines. The
cert URL's host is restricted to ``sns.<region>.amazonaws.com`` so a
forged envelope can't point verification at an attacker-controlled cert.
"""
import json
import re
from urllib.parse import urlparse
from urllib.request import urlopen

from .base_provider import CanonicalDeliveryEvent, NewsletterProviderAdapter

CONFIG_PARAM_TOPIC_ARN = "newsletter_compliance.ses_sns_topic_arn"

_SNS_HOST_RE = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com$")

_SES_EVENT_TYPE_MAP = {
    "Send": "accepted",
    "Delivery": "delivered",
    "DeliveryDelay": "delivery_delayed",
    "Complaint": "complaint",
    "Bounce": "hard_bounce",  # refined via bounceType below
    "Reject": "provider_rejected",
}


class SesProviderAdapter(NewsletterProviderAdapter):
    provider_code = "ses"

    def __init__(self, env):
        self.env = env

    def _get_allowed_topic_arn(self):
        return self.env["ir.config_parameter"].sudo().get_param(CONFIG_PARAM_TOPIC_ARN)

    def validate_webhook(self, headers, body):
        allowed_topic_arn = self._get_allowed_topic_arn()
        if not allowed_topic_arn:
            return False

        try:
            envelope = json.loads(body)
        except (ValueError, TypeError):
            return False

        if envelope.get("TopicArn") != allowed_topic_arn:
            return False

        try:
            return self._verify_sns_signature(envelope)
        except Exception:  # noqa: BLE001 - any verification failure is a rejection
            return False

    def _verify_sns_signature(self, envelope):
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.x509 import load_pem_x509_certificate

        cert_url = envelope.get("SigningCertURL", "")
        parsed = urlparse(cert_url)
        if parsed.scheme != "https" or not _SNS_HOST_RE.match(parsed.netloc):
            return False

        message_type = envelope.get("Type")
        if message_type in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
            fields = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]
        else:
            fields = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]

        parts = []
        for field_name in fields:
            if field_name == "Subject" and "Subject" not in envelope:
                continue
            if field_name not in envelope:
                return False
            parts.append(f"{field_name}\n{envelope[field_name]}\n")
        signing_string = "".join(parts).encode("utf-8")

        import base64

        signature = base64.b64decode(envelope.get("Signature", ""))
        signature_version = envelope.get("SignatureVersion", "1")
        digest_algorithm = hashes.SHA256() if signature_version == "2" else hashes.SHA1()

        with urlopen(cert_url, timeout=5) as response:  # noqa: S310 - host allowlisted above
            cert_pem = response.read()
        certificate = load_pem_x509_certificate(cert_pem)
        public_key = certificate.public_key()

        try:
            public_key.verify(signature, signing_string, padding.PKCS1v15(), digest_algorithm)
            return True
        except InvalidSignature:
            return False

    def normalize_event(self, payload):
        if isinstance(payload, (bytes, str)):
            payload = json.loads(payload)

        envelope = payload
        message_raw = envelope.get("Message")
        if message_raw is None:
            # Already-unwrapped SES event (e.g. a test fixture) rather than
            # a full SNS envelope.
            ses_event = envelope
        else:
            ses_event = json.loads(message_raw) if isinstance(message_raw, str) else message_raw

        ses_event_type = ses_event.get("eventType") or ses_event.get("notificationType", "")
        event_type = _SES_EVENT_TYPE_MAP.get(ses_event_type, "unknown")

        bounce = ses_event.get("bounce") or {}
        bounce_type = None
        if ses_event_type == "Bounce":
            bounce_type = "permanent" if bounce.get("bounceType") == "Permanent" else "transient"
            event_type = "hard_bounce" if bounce_type == "permanent" else "soft_bounce"

        mail = ses_event.get("mail") or {}
        recipients = mail.get("destination") or []
        bounced_recipients = bounce.get("bouncedRecipients") or []
        complaint = ses_event.get("complaint") or {}
        complained_recipients = complaint.get("complainedRecipients") or []

        email = None
        diagnostic_code = None
        smtp_status = None
        if bounced_recipients:
            email = bounced_recipients[0].get("emailAddress")
            diagnostic_code = bounced_recipients[0].get("diagnosticCode")
            smtp_status = bounced_recipients[0].get("status")
        elif complained_recipients:
            email = complained_recipients[0].get("emailAddress")
        elif recipients:
            email = recipients[0]

        return [
            CanonicalDeliveryEvent(
                provider=self.provider_code,
                provider_event_id=envelope.get("MessageId", ""),
                provider_message_id=mail.get("messageId"),
                event_type=event_type,
                event_timestamp=ses_event.get("mail", {}).get("timestamp")
                or envelope.get("Timestamp", ""),
                email=email,
                bounce_type=bounce_type,
                smtp_status=smtp_status,
                diagnostic_code=diagnostic_code,
                raw_payload=ses_event,
            )
        ]

    def classify_bounce(self, canonical_event):
        if canonical_event.bounce_type == "permanent":
            return "hard"
        if canonical_event.bounce_type == "transient":
            return "soft"
        return "unknown"
