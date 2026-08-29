from odoo import fields
from odoo.tests.common import HttpCase, TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import consent_service, subscribe_service


@tagged("post_install", "-at_install")
class TestNewsletterSubscribeService(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.public_purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Public Purpose",
                "code": "PUBLIC_PURPOSE",
                "privacy_notice_version": "v1",
                "public_subscribe": True,
            }
        )
        cls.internal_purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Internal Only Purpose",
                "code": "INTERNAL_PURPOSE",
                "privacy_notice_version": "v1",
                "public_subscribe": False,
            }
        )

    def test_get_public_purposes_excludes_internal_only(self):
        purposes = subscribe_service.get_public_purposes(self.env)
        self.assertIn(self.public_purpose, purposes)
        self.assertNotIn(self.internal_purpose, purposes)

    def test_submit_request_creates_pending_consent_with_shared_token(self):
        partner, records, token = subscribe_service.submit_request(
            self.env, "new.subscriber@example.com", "New", "Subscriber",
            [self.public_purpose.id],
        )
        self.assertTrue(partner)
        self.assertEqual(len(records), 1)
        self.assertEqual(records.status, "pending")
        self.assertEqual(records.confirmation_token, token)
        self.assertFalse(records.given_at)

    def test_submit_request_rejects_internal_only_purpose(self):
        partner, records, token = subscribe_service.submit_request(
            self.env, "blocked@example.com", "Blocked", "User",
            [self.internal_purpose.id],
        )
        self.assertFalse(partner)
        self.assertFalse(records)
        self.assertFalse(token)

    def test_submit_request_multiple_purposes_share_one_token(self):
        second_purpose = self.env["newsletter.consent.purpose"].create(
            {
                "name": "Second Public Purpose",
                "code": "SECOND_PUBLIC_PURPOSE",
                "privacy_notice_version": "v1",
                "public_subscribe": True,
            }
        )
        _partner, records, token = subscribe_service.submit_request(
            self.env, "multi@example.com", "Multi", "Purpose",
            [self.public_purpose.id, second_purpose.id],
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(set(records.mapped("confirmation_token")), {token})

    def test_submit_request_reuses_existing_partner_by_email(self):
        existing = self.env["res.partner"].create(
            {"name": "Existing Contact", "email": "existing@example.com"}
        )
        partner, _records, _token = subscribe_service.submit_request(
            self.env, "existing@example.com", "Ignored", "Name",
            [self.public_purpose.id],
        )
        self.assertEqual(partner, existing)

    def test_confirm_token_activates_pending_consent(self):
        _partner, records, token = subscribe_service.submit_request(
            self.env, "confirm.me@example.com", "Confirm", "Me",
            [self.public_purpose.id],
        )
        activated = subscribe_service.confirm_token(self.env, token)
        self.assertEqual(activated, records)
        records.invalidate_recordset()
        self.assertEqual(records.status, "active")
        self.assertTrue(records.given_at)

    def test_confirm_token_is_a_noop_when_already_confirmed(self):
        _partner, records, token = subscribe_service.submit_request(
            self.env, "double.confirm@example.com", "Double", "Confirm",
            [self.public_purpose.id],
        )
        subscribe_service.confirm_token(self.env, token)
        second_attempt = subscribe_service.confirm_token(self.env, token)
        self.assertFalse(second_attempt)

    def test_confirm_token_unknown_token_returns_empty(self):
        result = subscribe_service.confirm_token(self.env, "does-not-exist")
        self.assertFalse(result)

    def test_pending_consent_is_not_eligibility_evidence_yet(self):
        """A pending (unconfirmed) consent record must never be treated as
        valid consent by the eligibility engine - it's not evidence until
        confirmed.
        """
        _partner, _records, _token = subscribe_service.submit_request(
            self.env, "not.yet.valid@example.com", "Not", "Yet",
            [self.public_purpose.id],
        )
        effective = consent_service.get_effective_consents_by_email(
            self.env, ["not.yet.valid@example.com"], self.public_purpose.id,
            self.env.company.id, fields.Datetime.now(),
        )
        self.assertNotIn("not.yet.valid@example.com", effective)


@tagged("post_install", "-at_install")
class TestNewsletterSubscribeController(HttpCase):
    def setUp(self):
        super().setUp()
        self.purpose = self.env["newsletter.consent.purpose"].create(
            {
                "name": "HTTP Subscribe Purpose",
                "code": "HTTP_SUBSCRIBE_PURPOSE",
                "privacy_notice_version": "v1",
                "public_subscribe": True,
            }
        )

    def test_get_form_lists_public_purpose(self):
        response = self.url_open("/newsletter-compliance/subscribe")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"HTTP Subscribe Purpose", response.content)

    def test_post_without_consent_checkbox_rejected(self):
        response = self.url_open(
            "/newsletter-compliance/subscribe",
            data={"email": "no.consent@example.com", "purpose_ids": [str(self.purpose.id)]},
        )
        self.assertEqual(response.status_code, 400)

    def test_full_double_opt_in_flow(self):
        post_response = self.url_open(
            "/newsletter-compliance/subscribe",
            data={
                "email": "flow.test@example.com",
                "first_name": "Flow",
                "last_name": "Test",
                "consent": "1",
                "purpose_ids": [str(self.purpose.id)],
            },
        )
        self.assertEqual(post_response.status_code, 200)
        self.assertIn(b"confirmation link", post_response.content)

        consent = self.env["newsletter.consent.record"].search(
            [("email_normalized", "=", "flow.test@example.com")]
        )
        self.assertTrue(consent)
        self.assertEqual(consent.status, "pending")
        self.assertTrue(consent.confirmation_token)

        confirm_response = self.url_open(
            f"/newsletter-compliance/subscribe/confirm/{consent.confirmation_token}"
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertIn(b"Subscription confirmed", confirm_response.content)

        consent.invalidate_recordset()
        self.assertEqual(consent.status, "active")

    def test_confirm_invalid_token_returns_400(self):
        response = self.url_open("/newsletter-compliance/subscribe/confirm/bogus-token")
        self.assertEqual(response.status_code, 400)
