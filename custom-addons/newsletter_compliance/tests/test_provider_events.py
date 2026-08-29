import hashlib
import hmac
import json
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services.providers.base_provider import (
    CanonicalDeliveryEvent,
)
from odoo.addons.newsletter_compliance.services.providers.generic_provider import (
    GenericProviderAdapter,
)


@tagged("post_install", "-at_install")
class TestNewsletterProviderEvents(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.generic_provider_secret", "test-secret"
        )

    def _sign(self, body):
        return "sha256=" + hmac.new(
            b"test-secret", body if isinstance(body, bytes) else body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def test_valid_signature_accepted(self):
        adapter = GenericProviderAdapter(self.env)
        body = json.dumps({"event_type": "delivered"})
        headers = {"X-Newsletter-Signature": self._sign(body)}
        self.assertTrue(adapter.validate_webhook(headers, body))

    def test_invalid_signature_rejected(self):
        adapter = GenericProviderAdapter(self.env)
        body = json.dumps({"event_type": "delivered"})
        headers = {"X-Newsletter-Signature": "sha256=deadbeef"}
        self.assertFalse(adapter.validate_webhook(headers, body))

    def test_missing_signature_header_rejected(self):
        adapter = GenericProviderAdapter(self.env)
        body = json.dumps({"event_type": "delivered"})
        self.assertFalse(adapter.validate_webhook({}, body))

    def test_no_secret_configured_fails_closed(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.generic_provider_secret", False
        )
        adapter = GenericProviderAdapter(self.env)
        body = json.dumps({"event_type": "delivered"})
        headers = {"X-Newsletter-Signature": self._sign(body)}
        self.assertFalse(adapter.validate_webhook(headers, body))

    def test_ingest_is_idempotent(self):
        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-idempotent-1",
            provider_message_id="msg-1",
            event_type="delivered",
            event_timestamp="2026-01-01T10:00:00",
            email="idem@example.com",
        )
        record1, created1 = self.env["newsletter.provider.event"].ingest("generic", event)
        record2, created2 = self.env["newsletter.provider.event"].ingest("generic", event)

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(record1.id, record2.id)

        count = self.env["newsletter.provider.event"].search_count(
            [("provider", "=", "generic"), ("provider_event_id", "=", "evt-idempotent-1")]
        )
        self.assertEqual(count, 1)

    def test_fallback_event_id_used_when_provider_omits_one(self):
        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="",
            provider_message_id="msg-2",
            event_type="soft_bounce",
            event_timestamp="2026-01-01T10:00:00",
            email="fallback@example.com",
        )
        record, created = self.env["newsletter.provider.event"].ingest("generic", event)
        self.assertTrue(created)
        self.assertTrue(record.provider_event_id)

    def test_unmatched_event_retained_not_discarded(self):
        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-unmatched-1",
            provider_message_id="no-such-message-id",
            event_type="delivered",
            event_timestamp="2026-01-01T10:00:00",
            email="unmatched@example.com",
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", event)
        record.process_event()

        self.assertEqual(record.processing_state, "unmatched")
        self.assertTrue(record.exists())
