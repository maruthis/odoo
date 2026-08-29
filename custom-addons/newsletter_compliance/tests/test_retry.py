from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import retry_service


@tagged("post_install", "-at_install")
class TestNewsletterRetryLogic(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Retry Purpose",
                "code": "RETRY_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Retry Brand",
                "code": "RETRY_BRAND",
                "email_from": "retry@example.com",
                "physical_address": "1 Retry St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Retry Test",
                "login": "operator_retry_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("mass_mailing.group_mass_mailing_user").id,
                            cls.env.ref(
                                "newsletter_compliance.group_newsletter_campaign_operator"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.approver = cls.env["res.users"].create(
            {
                "name": "Approver Retry Test",
                "login": "approver_retry_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("mass_mailing.group_mass_mailing_user").id,
                            cls.env.ref(
                                "newsletter_compliance.group_newsletter_content_approver"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "Reviewer Retry Test",
                "login": "reviewer_retry_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("mass_mailing.group_mass_mailing_user").id,
                            cls.env.ref(
                                "newsletter_compliance.group_newsletter_compliance_reviewer"
                            ).id,
                        ],
                    )
                ],
            }
        )

    def test_backoff_doubles_and_caps(self):
        self.assertEqual(retry_service.calculate_next_retry_delay(1), 60)
        self.assertEqual(retry_service.calculate_next_retry_delay(2), 120)
        self.assertEqual(retry_service.calculate_next_retry_delay(3), 240)
        self.assertEqual(retry_service.calculate_next_retry_delay(4), 480)
        self.assertEqual(retry_service.calculate_next_retry_delay(5), 960)
        # far beyond max should cap, not overflow
        self.assertEqual(retry_service.calculate_next_retry_delay(20), 3600)

    def test_classify_error_retryable_vs_not(self):
        self.assertTrue(retry_service.classify_error("Connection timed out"))
        self.assertTrue(retry_service.classify_error("451 Temporary local problem"))
        self.assertFalse(retry_service.classify_error("550 Mailbox does not exist"))
        self.assertFalse(retry_service.classify_error("some totally unknown error"))

    def _make_partner_with_consent(self, name, email):
        partner = self.env["res.partner"].create({"name": name, "email": email})
        self.env["newsletter.consent.record"].create(
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
        return partner

    def _create_queued_run(self, partner_ids):
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Retry Campaign",
                "subject": "Retry Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner_ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "retry@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.reviewer).action_run_compliance_preflight()
        run = campaign.current_campaign_run_id
        run.with_user(self.operator).action_start_execution()
        return run

    def test_temporary_error_sets_retry_pending(self):
        partner = self._make_partner_with_consent("Retry Temp", "retry.temp@example.com")
        run = self._create_queued_run(partner.ids)

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": False,
                "provider_message_id": False,
                "error_code": "SMTPConnectError",
                "error_message": "Connection timed out",
                "retryable": True,
            }
            run._process_next_dispatch_batch()

        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        self.assertEqual(eligibility.dispatch_state, "retry_pending")
        self.assertEqual(eligibility.dispatch_attempt_count, 1)
        self.assertTrue(eligibility.next_retry_at)

    def test_eventual_success_after_retry(self):
        partner = self._make_partner_with_consent("Retry Success", "retry.success@example.com")
        run = self._create_queued_run(partner.ids)

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": False,
                "provider_message_id": False,
                "error_code": "SMTPConnectError",
                "error_message": "Connection timed out",
                "retryable": True,
            }
            run._process_next_dispatch_batch()

        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        self.assertEqual(eligibility.dispatch_state, "retry_pending")

        # simulate the retry delay having elapsed
        eligibility.with_context(skip_eligibility_freeze_guard=True).write(
            {"next_retry_at": False}
        )

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "retry-success-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        self.assertEqual(eligibility.dispatch_state, "sent")
        self.assertEqual(eligibility.dispatch_attempt_count, 2)

    def test_maximum_retries_exceeded_fails(self):
        partner = self._make_partner_with_consent("Retry Max", "retry.max@example.com")
        run = self._create_queued_run(partner.ids)
        run.write({"maximum_retry_count": 2})

        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")

        # attempt 1: attempt_count -> 1, 1 < 2 -> retry_pending
        # attempt 2: attempt_count -> 2, 2 < 2 is False -> failed (cap reached)
        for _ in range(2):
            eligibility.with_context(skip_eligibility_freeze_guard=True).write(
                {"next_retry_at": False}
            )
            with patch(
                "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
            ) as mock_send:
                mock_send.return_value = {
                    "accepted": False,
                    "provider_message_id": False,
                    "error_code": "SMTPConnectError",
                    "error_message": "Connection timed out",
                    "retryable": True,
                }
                run._process_next_dispatch_batch()

        self.assertEqual(eligibility.dispatch_state, "failed")
        self.assertEqual(eligibility.dispatch_attempt_count, 2)

    def test_non_retryable_error_fails_immediately(self):
        partner = self._make_partner_with_consent(
            "Retry Permanent", "retry.permanent@example.com"
        )
        run = self._create_queued_run(partner.ids)

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": False,
                "provider_message_id": False,
                "error_code": "SMTPRecipientsRefused",
                "error_message": "550 Mailbox does not exist",
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        self.assertEqual(eligibility.dispatch_state, "failed")
        self.assertEqual(eligibility.dispatch_attempt_count, 1)
        self.assertFalse(eligibility.last_error_retryable)
