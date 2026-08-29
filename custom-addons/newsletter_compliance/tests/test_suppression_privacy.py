import datetime

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import suppression_service


@tagged("post_install", "-at_install")
class TestNewsletterSuppressionPrivacy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason = cls.env.ref("newsletter_compliance.suppression_reason_manual")

    def test_opt_out_survives_pseudonymization(self):
        """The core R6 guarantee: once a suppression entry is
        pseudonymized (identity link removed), it must still block the
        same email address if that email is re-imported/re-submitted -
        the HMAC token, not the plain email or partner_id, is what the
        eligibility engine actually matches against.
        """
        partner = self.env["res.partner"].create(
            {"name": "Survives Erasure", "email": "survives.erasure@example.com"}
        )
        entry = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )

        before = suppression_service.get_applicable_suppressions_by_email(
            self.env,
            ["survives.erasure@example.com"],
            purpose_id=False,
            mailing_list_ids=[],
            evaluation_time=fields.Datetime.now() + datetime.timedelta(days=1),
        )
        self.assertIn("survives.erasure@example.com", before)
        self.assertEqual(before["survives.erasure@example.com"], entry)

        entry.pseudonymize(reference="erasure-test-1")
        self.assertFalse(entry.partner_id)
        self.assertFalse(entry.email_normalized)
        self.assertEqual(entry.identity_state, "pseudonymized")

        after = suppression_service.get_applicable_suppressions_by_email(
            self.env,
            ["survives.erasure@example.com"],
            purpose_id=False,
            mailing_list_ids=[],
            evaluation_time=fields.Datetime.now() + datetime.timedelta(days=1),
        )
        self.assertIn("survives.erasure@example.com", after)
        self.assertEqual(after["survives.erasure@example.com"], entry)

    def test_pseudonymized_entry_cannot_be_reidentified_without_partner(self):
        partner = self.env["res.partner"].create(
            {"name": "Anon Check", "email": "anon.check@example.com"}
        )
        entry = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )
        entry.pseudonymize()
        self.assertFalse(entry.partner_id)
        self.assertFalse(entry.email_normalized)
        self.assertTrue(entry.email_hash)

    def test_pseudonymize_is_idempotent(self):
        partner = self.env["res.partner"].create(
            {"name": "Idempotent Check", "email": "idempotent.check@example.com"}
        )
        entry = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )
        entry.pseudonymize()
        first_pseudonymized_at = entry.pseudonymized_at
        entry.pseudonymize()
        self.assertEqual(entry.pseudonymized_at, first_pseudonymized_at)
