import base64
import hashlib
import hmac
import json

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services.providers.mailgun_provider import (
    CONFIG_PARAM_SIGNING_KEY as MAILGUN_KEY_PARAM,
    MailgunProviderAdapter,
)
from odoo.addons.newsletter_compliance.services.providers.sendgrid_provider import (
    CONFIG_PARAM_PUBLIC_KEY as SENDGRID_KEY_PARAM,
    SendGridProviderAdapter,
)
from odoo.addons.newsletter_compliance.services.providers.ses_provider import SesProviderAdapter
from odoo.addons.newsletter_compliance.services.providers.smtp_provider import (
    CONFIG_PARAM_SECRET as SMTP_SECRET_PARAM,
    SmtpProviderAdapter,
)
from odoo.addons.newsletter_compliance.services.providers import registry


@tagged("post_install", "-at_install")
class TestNewsletterProviderRegistry(TransactionCase):
    def test_all_four_new_providers_registered(self):
        registered = registry.get_registered_providers()
        for code in ("smtp", "ses", "sendgrid", "mailgun"):
            self.assertIn(code, registered)
            self.assertIsNotNone(registry.get_provider_adapter(self.env, code))


@tagged("post_install", "-at_install")
class TestNewsletterMailgunAdapter(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(MAILGUN_KEY_PARAM, "mg-signing-key")
        self.adapter = MailgunProviderAdapter(self.env)

    def _signed_payload(self, event_data):
        timestamp = "1690000000"
        token = "mg-token-1"
        signature = hmac.new(
            b"mg-signing-key", f"{timestamp}{token}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return json.dumps(
            {
                "signature": {"timestamp": timestamp, "token": token, "signature": signature},
                "event-data": event_data,
            }
        ).encode("utf-8")

    def test_valid_signature_accepted(self):
        body = self._signed_payload({"event": "delivered", "timestamp": 1690000000})
        self.assertTrue(self.adapter.validate_webhook({}, body))

    def test_invalid_signature_rejected(self):
        body = self._signed_payload({"event": "delivered", "timestamp": 1690000000})
        payload = json.loads(body)
        payload["signature"]["signature"] = "0" * 64
        self.assertFalse(self.adapter.validate_webhook({}, json.dumps(payload).encode("utf-8")))

    def test_no_secret_configured_rejects(self):
        self.env["ir.config_parameter"].sudo().set_param(MAILGUN_KEY_PARAM, False)
        body = self._signed_payload({"event": "delivered", "timestamp": 1690000000})
        self.assertFalse(self.adapter.validate_webhook({}, body))

    def test_normalize_hard_bounce(self):
        body = self._signed_payload(
            {
                "event": "failed",
                "severity": "permanent",
                "timestamp": 1690000000,
                "recipient": "bounced@example.com",
                "id": "mg-evt-1",
                "message": {"headers": {"message-id": "mg-msg-1"}},
                "delivery-status": {"code": 550, "description": "mailbox unavailable"},
            }
        )
        events = self.adapter.normalize_event(body)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "hard_bounce")
        self.assertEqual(events[0].bounce_type, "permanent")
        self.assertEqual(self.adapter.classify_bounce(events[0]), "hard")
        self.assertTrue(events[0].event_timestamp)

    def test_normalize_soft_bounce(self):
        body = self._signed_payload(
            {"event": "failed", "severity": "temporary", "timestamp": 1690000000, "id": "mg-evt-2"}
        )
        events = self.adapter.normalize_event(body)
        self.assertEqual(events[0].event_type, "soft_bounce")
        self.assertEqual(self.adapter.classify_bounce(events[0]), "soft")


@tagged("post_install", "-at_install")
class TestNewsletterSendGridAdapter(TransactionCase):
    def setUp(self):
        super().setUp()
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        self.private_key = Ed25519PrivateKey.generate()
        public_bytes = self.private_key.public_key().public_bytes_raw()
        self.env["ir.config_parameter"].sudo().set_param(
            SENDGRID_KEY_PARAM, base64.b64encode(public_bytes).decode("ascii")
        )
        self.adapter = SendGridProviderAdapter(self.env)

    def _sign(self, body, timestamp="1690000000"):
        signed_payload = timestamp.encode("utf-8") + body
        signature = self.private_key.sign(signed_payload)
        return {
            "X-Twilio-Email-Event-Webhook-Signature": base64.b64encode(signature).decode("ascii"),
            "X-Twilio-Email-Event-Webhook-Timestamp": timestamp,
        }

    def test_valid_signature_accepted(self):
        body = json.dumps([{"event": "delivered"}]).encode("utf-8")
        headers = self._sign(body)
        self.assertTrue(self.adapter.validate_webhook(headers, body))

    def test_invalid_signature_rejected(self):
        body = json.dumps([{"event": "delivered"}]).encode("utf-8")
        headers = self._sign(body)
        tampered_body = json.dumps([{"event": "bounce"}]).encode("utf-8")
        self.assertFalse(self.adapter.validate_webhook(headers, tampered_body))

    def test_missing_headers_rejected(self):
        body = json.dumps([{"event": "delivered"}]).encode("utf-8")
        self.assertFalse(self.adapter.validate_webhook({}, body))

    def test_normalize_hard_bounce_vs_soft_bounce(self):
        events = self.adapter.normalize_event(
            [
                {
                    "event": "bounce",
                    "type": "bounce",
                    "sg_event_id": "sg-1",
                    "email": "hard@example.com",
                    "timestamp": 1690000000,
                },
                {
                    "event": "bounce",
                    "type": "blocked",
                    "sg_event_id": "sg-2",
                    "email": "soft@example.com",
                    "timestamp": 1690000000,
                },
            ]
        )
        self.assertEqual(events[0].event_type, "hard_bounce")
        self.assertEqual(self.adapter.classify_bounce(events[0]), "hard")
        self.assertEqual(events[1].event_type, "soft_bounce")
        self.assertEqual(self.adapter.classify_bounce(events[1]), "soft")

    def test_normalize_delivered(self):
        events = self.adapter.normalize_event(
            [{"event": "delivered", "sg_event_id": "sg-3", "email": "ok@example.com"}]
        )
        self.assertEqual(events[0].event_type, "delivered")


@tagged("post_install", "-at_install")
class TestNewsletterSmtpAdapter(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(SMTP_SECRET_PARAM, "smtp-relay-secret")
        self.adapter = SmtpProviderAdapter(self.env)

    def test_valid_signature_accepted(self):
        body = json.dumps({"event_type": "hard_bounce", "email": "x@example.com"}).encode("utf-8")
        signature = hmac.new(b"smtp-relay-secret", body, hashlib.sha256).hexdigest()
        headers = {"X-Newsletter-Signature": f"sha256={signature}"}
        self.assertTrue(self.adapter.validate_webhook(headers, body))

    def test_invalid_signature_rejected(self):
        body = json.dumps({"event_type": "hard_bounce"}).encode("utf-8")
        headers = {"X-Newsletter-Signature": "sha256=" + "0" * 64}
        self.assertFalse(self.adapter.validate_webhook(headers, body))

    def test_normalize_event(self):
        body = json.dumps(
            {
                "provider_event_id": "smtp-1",
                "event_type": "soft_bounce",
                "bounce_type": "transient",
                "email": "relay@example.com",
            }
        ).encode("utf-8")
        events = self.adapter.normalize_event(body)
        self.assertEqual(events[0].event_type, "soft_bounce")
        self.assertEqual(self.adapter.classify_bounce(events[0]), "soft")


@tagged("post_install", "-at_install")
class TestNewsletterSesAdapter(TransactionCase):
    """SNS signature verification requires fetching a certificate over the
    network (real AWS behavior), so only the pure payload-normalization
    logic is exercised here - validate_webhook's crypto path is not
    covered by these offline tests.
    """

    def setUp(self):
        super().setUp()
        self.adapter = SesProviderAdapter(self.env)

    def test_normalize_hard_bounce_from_unwrapped_event(self):
        ses_event = {
            "eventType": "Bounce",
            "bounce": {
                "bounceType": "Permanent",
                "bouncedRecipients": [
                    {
                        "emailAddress": "ses.hard@example.com",
                        "diagnosticCode": "smtp; 550 mailbox unavailable",
                        "status": "5.1.1",
                    }
                ],
            },
            "mail": {"messageId": "ses-msg-1", "timestamp": "2026-01-01T10:00:00.000Z"},
        }
        events = self.adapter.normalize_event({"MessageId": "sns-msg-1", "Message": json.dumps(ses_event)})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "hard_bounce")
        self.assertEqual(events[0].bounce_type, "permanent")
        self.assertEqual(events[0].email, "ses.hard@example.com")
        self.assertEqual(self.adapter.classify_bounce(events[0]), "hard")

    def test_normalize_soft_bounce(self):
        ses_event = {
            "eventType": "Bounce",
            "bounce": {
                "bounceType": "Transient",
                "bouncedRecipients": [{"emailAddress": "ses.soft@example.com"}],
            },
            "mail": {"messageId": "ses-msg-2"},
        }
        events = self.adapter.normalize_event({"Message": json.dumps(ses_event)})
        self.assertEqual(events[0].event_type, "soft_bounce")
        self.assertEqual(self.adapter.classify_bounce(events[0]), "soft")

    def test_normalize_complaint(self):
        ses_event = {
            "eventType": "Complaint",
            "complaint": {"complainedRecipients": [{"emailAddress": "ses.complaint@example.com"}]},
            "mail": {"messageId": "ses-msg-3"},
        }
        events = self.adapter.normalize_event({"Message": json.dumps(ses_event)})
        self.assertEqual(events[0].event_type, "complaint")
        self.assertEqual(events[0].email, "ses.complaint@example.com")

    def test_normalize_delivery(self):
        ses_event = {
            "eventType": "Delivery",
            "mail": {"messageId": "ses-msg-4", "destination": ["delivered@example.com"]},
        }
        events = self.adapter.normalize_event({"Message": json.dumps(ses_event)})
        self.assertEqual(events[0].event_type, "delivered")
        self.assertEqual(events[0].email, "delivered@example.com")

    def test_validate_webhook_rejects_without_configured_topic_arn(self):
        body = json.dumps({"TopicArn": "arn:aws:sns:us-east-1:123:topic"}).encode("utf-8")
        self.assertFalse(self.adapter.validate_webhook({}, body))

    def test_validate_webhook_rejects_mismatched_topic_arn(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.ses_sns_topic_arn", "arn:aws:sns:us-east-1:123:allowed-topic"
        )
        body = json.dumps({"TopicArn": "arn:aws:sns:us-east-1:123:other-topic"}).encode("utf-8")
        self.assertFalse(self.adapter.validate_webhook({}, body))
