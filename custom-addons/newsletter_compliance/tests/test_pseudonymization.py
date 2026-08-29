from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import pseudonymization_service


@tagged("post_install", "-at_install")
class TestNewsletterPseudonymization(TransactionCase):
    def test_hmac_token_is_deterministic_and_normalized(self):
        token_a = pseudonymization_service.hmac_token(self.env, "Person@Example.com")
        token_b = pseudonymization_service.hmac_token(self.env, " person@example.com ")
        self.assertEqual(token_a, token_b)
        self.assertTrue(token_a.startswith("v1:"))

    def test_hmac_token_differs_per_value(self):
        token_a = pseudonymization_service.hmac_token(self.env, "one@example.com")
        token_b = pseudonymization_service.hmac_token(self.env, "two@example.com")
        self.assertNotEqual(token_a, token_b)

    def test_tokens_match_validates_correctly(self):
        token = pseudonymization_service.hmac_token(self.env, "check@example.com")
        self.assertTrue(pseudonymization_service.tokens_match(self.env, "check@example.com", token))
        self.assertFalse(pseudonymization_service.tokens_match(self.env, "other@example.com", token))
        self.assertFalse(pseudonymization_service.tokens_match(self.env, "check@example.com", False))

    def test_secret_persists_across_calls(self):
        first = pseudonymization_service.hmac_token(self.env, "secret-stability@example.com")
        # Force a fresh read of the config parameter to make sure the
        # secret was actually persisted rather than regenerated per call.
        self.env["ir.config_parameter"].invalidate_model()
        second = pseudonymization_service.hmac_token(self.env, "secret-stability@example.com")
        self.assertEqual(first, second)

    def test_suppression_entry_stores_email_hash_on_create(self):
        partner = self.env["res.partner"].create(
            {"name": "Hash Test", "email": "hash.test@example.com"}
        )
        reason = self.env.ref("newsletter_compliance.suppression_reason_manual")
        entry = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": reason.id,
                "source": "manual",
            }
        )
        expected_hash = pseudonymization_service.hmac_token(self.env, "hash.test@example.com")
        self.assertEqual(entry.email_hash, expected_hash)
        self.assertEqual(entry.identity_state, "identified")
