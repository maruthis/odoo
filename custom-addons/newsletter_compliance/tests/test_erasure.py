from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterErasure(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Erasure Purpose",
                "code": "ERASURE_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.reason = cls.env.ref("newsletter_compliance.suppression_reason_manual")

    def _make_subject(self, email):
        partner = self.env["res.partner"].create({"name": email, "email": email})
        consent = self.env["newsletter.consent.record"].create(
            {
                "partner_id": partner.id,
                "purpose_id": self.purpose.id,
                "status": "active",
                "given_at": "2026-01-01 10:00:00",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )
        suppression = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )
        return partner, consent, suppression

    def test_erasure_execution_requires_identity_verification(self):
        partner, _consent, _suppression = self._make_subject("unverified.erasure@example.com")
        request = self.env["newsletter.privacy.request"].create(
            {
                "request_type": "erasure",
                "partner_id": partner.id,
                "email_normalized": "unverified.erasure@example.com",
            }
        )
        with self.assertRaises(UserError):
            request.action_execute()

    def test_erasure_pseudonymizes_suppression_but_retains_consent(self):
        partner, consent, suppression = self._make_subject("full.erasure@example.com")
        request = self.env["newsletter.privacy.request"].create(
            {
                "request_type": "erasure",
                "partner_id": partner.id,
                "email_normalized": "full.erasure@example.com",
            }
        )
        request.action_verify_identity("email_confirmation")
        request.action_run_discovery()
        results = request.action_execute()

        suppression.invalidate_recordset()
        self.assertEqual(suppression.identity_state, "pseudonymized")
        self.assertFalse(suppression.partner_id)

        # Consent record must survive as regulatory evidence - erasure of
        # opt-in/opt-out history is explicitly not permitted (R6-BR-05).
        self.assertTrue(consent.exists())

        actions = self.env["newsletter.retention.action"].search(
            [("privacy_request_id", "=", request.id)]
        )
        self.assertTrue(actions)
        pseudonymize_actions = actions.filtered(lambda a: a.action_type == "pseudonymize")
        retain_actions = actions.filtered(lambda a: a.action_type == "retain")
        self.assertTrue(pseudonymize_actions)
        self.assertTrue(retain_actions)

        result_actions = {r["model"]: r["action"] for r in results}
        self.assertEqual(result_actions.get("newsletter.suppression.entry"), "pseudonymize")
        self.assertEqual(result_actions.get("newsletter.consent.record"), "retained_audit_evidence")

    def test_erasure_blocked_by_legal_hold(self):
        partner, _consent, suppression = self._make_subject("held.erasure@example.com")
        self.env["newsletter.legal.hold"].create(
            {
                "name": "Erasure Block Hold",
                "reason": "Litigation preservation",
                "scope_type": "recipient",
                "scope_partner_ids": [(6, 0, [partner.id])],
            }
        )
        request = self.env["newsletter.privacy.request"].create(
            {
                "request_type": "erasure",
                "partner_id": partner.id,
                "email_normalized": "held.erasure@example.com",
            }
        )
        request.action_verify_identity("email_confirmation")
        request.action_run_discovery()
        request.action_execute()

        suppression.invalidate_recordset()
        self.assertEqual(suppression.identity_state, "identified")
        self.assertTrue(suppression.partner_id)

        blocked = self.env["newsletter.retention.action"].search(
            [("privacy_request_id", "=", request.id), ("result", "=", "blocked")]
        )
        self.assertTrue(blocked)

    def test_action_complete_requires_recorded_actions(self):
        partner, _consent, _suppression = self._make_subject("incomplete.erasure@example.com")
        request = self.env["newsletter.privacy.request"].create(
            {
                "request_type": "erasure",
                "partner_id": partner.id,
                "email_normalized": "incomplete.erasure@example.com",
            }
        )
        with self.assertRaises(UserError):
            request.action_complete()

    def test_access_request_does_not_mutate_data(self):
        partner, _consent, suppression = self._make_subject("access.request@example.com")
        request = self.env["newsletter.privacy.request"].create(
            {
                "request_type": "access",
                "partner_id": partner.id,
                "email_normalized": "access.request@example.com",
            }
        )
        request.action_execute()
        suppression.invalidate_recordset()
        self.assertEqual(suppression.identity_state, "identified")
        self.assertEqual(request.status, "execution")
