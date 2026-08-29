from odoo.tests.common import HttpCase, TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import unsubscribe_service, unsubscribe_token_service


@tagged("post_install", "-at_install")
class TestNewsletterUnsubscribeToken(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Unsubscribe Purpose",
                "code": "UNSUB_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Unsubscribe Brand",
                "code": "UNSUB_BRAND",
                "email_from": "unsub@example.com",
                "physical_address": "1 Unsub St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {"name": "Unsub Recipient", "email": "unsub.recipient@example.com"}
        )
        cls.mailing = cls.env["mailing.mailing"].create(
            {
                "name": "Unsubscribe Campaign",
                "subject": "Unsubscribe Subject",
                "mailing_type": "mail",
                "mailing_model_id": cls.env["ir.model"]._get("res.partner").id,
                "mailing_domain": repr([("id", "in", cls.partner.ids)]),
                "brand_id": cls.brand.id,
                "consent_purpose_id": cls.purpose.id,
                "email_from": "unsub@example.com",
                "body_html": "<p>Content</p>",
            }
        )

    def test_token_roundtrip(self):
        token = unsubscribe_token_service.generate_token(
            self.env, self.partner.id, self.mailing.id
        )
        parsed = unsubscribe_token_service.parse_token(self.env, token)
        self.assertEqual(parsed, {"partner_id": self.partner.id, "mailing_id": self.mailing.id})

    def test_tampered_token_is_rejected(self):
        token = unsubscribe_token_service.generate_token(
            self.env, self.partner.id, self.mailing.id
        )
        payload_b64, _, signature = token.partition(".")
        tampered = f"{payload_b64}.{signature[::-1]}"
        self.assertIsNone(unsubscribe_token_service.parse_token(self.env, tampered))

    def test_garbage_token_is_rejected(self):
        self.assertIsNone(unsubscribe_token_service.parse_token(self.env, "not-a-real-token"))
        self.assertIsNone(unsubscribe_token_service.parse_token(self.env, ""))
        self.assertIsNone(unsubscribe_token_service.parse_token(self.env, None))

    def test_unsubscribe_all_marketing_creates_global_suppression_and_blacklist(self):
        entry = unsubscribe_service.process_choice(self.env, self.partner, self.mailing, "all")
        self.assertEqual(entry.scope, "global")
        self.assertEqual(entry.reason_id.code, "GLOBAL_OPT_OUT")
        blacklisted = self.env["mail.blacklist"].search(
            [("email", "=", "unsub.recipient@example.com")]
        )
        self.assertTrue(blacklisted)

    def test_unsubscribe_purpose_withdraws_consent_and_suppresses_purpose(self):
        consent = self.env["newsletter.consent.record"].create(
            {
                "partner_id": self.partner.id,
                "purpose_id": self.purpose.id,
                "status": "active",
                "given_at": "2026-01-01 10:00:00",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )
        entry = unsubscribe_service.process_choice(self.env, self.partner, self.mailing, "purpose")
        self.assertEqual(entry.scope, "purpose")
        self.assertEqual(entry.purpose_id, self.purpose)
        consent.invalidate_recordset()
        self.assertEqual(consent.status, "withdrawn")

    def test_unsubscribe_newsletter_only_falls_back_to_purpose_when_no_list(self):
        # This mailing targets by domain, not a mailing.list, so "newsletter
        # only" has no list to scope to and must fall back to purpose scope
        # rather than silently doing nothing.
        entry = unsubscribe_service.process_choice(self.env, self.partner, self.mailing, "list")
        self.assertEqual(entry.scope, "purpose")
        self.assertEqual(entry.purpose_id, self.purpose)

    def test_unsubscribe_newsletter_only_scopes_to_mailing_list_when_present(self):
        mailing_list = self.env["mailing.list"].create({"name": "Unsub Test List"})
        self.mailing.write({"contact_list_ids": [(6, 0, [mailing_list.id])]})
        entry = unsubscribe_service.process_choice(self.env, self.partner, self.mailing, "list")
        self.assertEqual(entry.scope, "mailing_list")
        self.assertEqual(entry.mailing_list_id, mailing_list)

    def test_unknown_choice_returns_none(self):
        self.assertIsNone(
            unsubscribe_service.process_choice(self.env, self.partner, self.mailing, "bogus")
        )


@tagged("post_install", "-at_install")
class TestNewsletterUnsubscribeController(HttpCase):
    def test_invalid_token_returns_400(self):
        response = self.url_open("/newsletter-compliance/unsubscribe/not-a-real-token")
        self.assertEqual(response.status_code, 400)

    def test_valid_token_get_shows_form_then_post_unsubscribes(self):
        purpose = self.env["newsletter.consent.purpose"].create(
            {
                "name": "HTTP Unsubscribe Purpose",
                "code": "HTTP_UNSUB_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        brand = self.env["newsletter.campaign.brand"].create(
            {
                "name": "HTTP Unsubscribe Brand",
                "code": "HTTP_UNSUB_BRAND",
                "email_from": "httpunsub@example.com",
                "physical_address": "1 HTTP St",
                "default_consent_purpose_id": purpose.id,
            }
        )
        partner = self.env["res.partner"].create(
            {"name": "HTTP Unsub Recipient", "email": "http.unsub@example.com"}
        )
        mailing = self.env["mailing.mailing"].create(
            {
                "name": "HTTP Unsubscribe Campaign",
                "subject": "HTTP Unsubscribe Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": brand.id,
                "consent_purpose_id": purpose.id,
                "email_from": "httpunsub@example.com",
                "body_html": "<p>Content</p>",
            }
        )

        token = unsubscribe_token_service.generate_token(self.env, partner.id, mailing.id)

        get_response = self.url_open(f"/newsletter-compliance/unsubscribe/{token}")
        self.assertEqual(get_response.status_code, 200)
        self.assertIn(b"Manage your email preferences", get_response.content)

        post_response = self.url_open(
            f"/newsletter-compliance/unsubscribe/{token}", data={"choice": "all"}
        )
        self.assertEqual(post_response.status_code, 200)
        self.assertIn(b"You have been unsubscribed", post_response.content)

        entry = self.env["newsletter.suppression.entry"].search(
            [("partner_id", "=", partner.id), ("scope", "=", "global")]
        )
        self.assertTrue(entry)
