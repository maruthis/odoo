from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterConsent(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "John Smith", "email": "john@example.com"}
        )
        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Healthcare Newsletter",
                "code": "HEALTHCARE",
                "privacy_notice_version": "v1",
            }
        )

    def _create_active_consent(self, **extra):
        vals = {
            "partner_id": self.partner.id,
            "purpose_id": self.purpose.id,
            "status": "active",
            "given_at": "2026-01-01 10:00:00",
            "source": "website",
            "channel": "web",
            "privacy_notice_version": "v1",
        }
        vals.update(extra)
        return self.env["newsletter.consent.record"].create(vals)

    def test_active_consent_requires_timestamp(self):
        with self.assertRaises(ValidationError):
            self._create_active_consent(given_at=False)

    def test_expiry_must_be_after_given_at(self):
        with self.assertRaises(ValidationError):
            self._create_active_consent(expires_at="2025-12-31 00:00:00")

    def test_consent_gets_unique_reference(self):
        consent = self._create_active_consent()
        self.assertTrue(consent.reference.startswith("CONS-"))

    def test_retention_mixin_fields_writable_on_active_consent(self):
        """R6 gap closure: consent_record now carries the real retention
        mixin (was previously missing entirely), so a retention policy can
        be stamped on it without touching protected evidence fields.
        """
        consent = self._create_active_consent()
        policy = self.env["newsletter.retention.policy"].create(
            {
                "name": "Consent Retention Test Policy",
                "code": "CONSENT_RETENTION_TEST",
                "data_category": "consent_evidence",
                "retention_period_days": 730,
                "expiry_action": "review",
            }
        )
        consent.write({"retention_policy_id": policy.id, "legal_hold": True})
        self.assertEqual(consent.retention_policy_id, policy)
        self.assertTrue(consent.legal_hold)
        with self.assertRaises(UserError):
            consent.write({"source": "phone"})

    def test_finalized_evidence_cannot_be_altered(self):
        consent = self._create_active_consent()
        with self.assertRaises(UserError):
            consent.write({"source": "phone"})

    def test_withdrawal_wizard_flow(self):
        consent = self._create_active_consent()
        wizard = self.env["newsletter.withdraw.consent.wizard"].create(
            {
                "consent_id": consent.id,
                "reason": "Recipient requested removal",
                "create_suppression": True,
                "suppression_scope": "purpose",
            }
        )
        wizard.action_confirm()

        self.assertEqual(consent.status, "withdrawn")
        self.assertTrue(consent.withdrawn_at)
        self.assertEqual(consent.withdrawal_reason, "Recipient requested removal")

        suppression = self.env["newsletter.suppression.entry"].search(
            [("partner_id", "=", self.partner.id)]
        )
        self.assertTrue(suppression)
        self.assertEqual(suppression.scope, "purpose")
        self.assertEqual(suppression.purpose_id, self.purpose)

    def test_withdrawn_consent_cannot_be_reactivated_directly(self):
        consent = self._create_active_consent()
        consent.write(
            {
                "status": "withdrawn",
                "withdrawn_at": "2026-02-01 10:00:00",
            }
        )
        with self.assertRaises(UserError):
            consent.write({"status": "active", "given_at": "2026-02-02 10:00:00"})

    def test_new_consent_can_supersede_withdrawn(self):
        old_consent = self._create_active_consent()
        old_consent.write(
            {"status": "withdrawn", "withdrawn_at": "2026-02-01 10:00:00"}
        )

        new_consent = self._create_active_consent(
            given_at="2026-02-05 10:00:00",
            supersedes_id=old_consent.id,
        )
        self.assertEqual(new_consent.supersedes_id, old_consent)

    def test_finalized_consent_cannot_be_deleted(self):
        consent = self._create_active_consent()
        with self.assertRaises(UserError):
            consent.unlink()
