import datetime

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterConsentExpiryCron(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Expiry Cron Test", "email": "expiry.cron@example.com"}
        )
        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Expiry Cron Purpose",
                "code": "EXPIRY_CRON_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )

    def _create_consent(self, given_at, expires_at=None):
        return self.env["newsletter.consent.record"].create(
            {
                "partner_id": self.partner.id,
                "purpose_id": self.purpose.id,
                "status": "active",
                "given_at": given_at,
                "expires_at": expires_at,
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )

    def test_cron_expires_past_due_active_consent(self):
        consent = self._create_consent(
            "2020-01-01 00:00:00", expires_at="2020-06-01 00:00:00"
        )
        self.env["newsletter.consent.record"]._cron_expire_consents()
        consent.invalidate_recordset()
        self.assertEqual(consent.status, "expired")

    def test_cron_leaves_future_expiry_untouched(self):
        future_expiry = fields.Datetime.now() + datetime.timedelta(days=30)
        consent = self._create_consent("2026-01-01 00:00:00", expires_at=future_expiry)
        self.env["newsletter.consent.record"]._cron_expire_consents()
        consent.invalidate_recordset()
        self.assertEqual(consent.status, "active")

    def test_cron_leaves_consent_without_expiry_untouched(self):
        consent = self._create_consent("2020-01-01 00:00:00", expires_at=False)
        self.env["newsletter.consent.record"]._cron_expire_consents()
        consent.invalidate_recordset()
        self.assertEqual(consent.status, "active")

    def test_cron_does_not_touch_already_withdrawn_consent(self):
        consent = self._create_consent(
            "2020-01-01 00:00:00", expires_at="2020-06-01 00:00:00"
        )
        consent.write(
            {
                "status": "withdrawn",
                "withdrawn_at": fields.Datetime.now(),
                "withdrawal_reason": "test",
                "withdrawal_source": "manual",
            }
        )
        self.env["newsletter.consent.record"]._cron_expire_consents()
        consent.invalidate_recordset()
        self.assertEqual(consent.status, "withdrawn")

    def test_expired_consent_already_excluded_from_effective_lookup_before_cron_runs(self):
        """The live domain check (not the cron) is what actually protects
        eligibility - confirm expiry is honored even before the cron ever
        runs, i.e. this is a reporting-accuracy improvement, not a
        correctness fix.
        """
        from odoo.addons.newsletter_compliance.services import consent_service

        self._create_consent("2020-01-01 00:00:00", expires_at="2020-06-01 00:00:00")
        effective = consent_service.get_effective_consents_by_email(
            self.env, ["expiry.cron@example.com"], self.purpose.id,
            self.env.company.id, fields.Datetime.now(),
        )
        self.assertNotIn("expiry.cron@example.com", effective)
