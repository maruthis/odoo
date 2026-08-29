from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterDispatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Dispatch Purpose",
                "code": "DISPATCH_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Dispatch Brand",
                "code": "DISPATCH_BRAND",
                "email_from": "dispatch@example.com",
                "physical_address": "1 Dispatch St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Dispatch Test",
                "login": "operator_dispatch_test",
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
                "name": "Approver Dispatch Test",
                "login": "approver_dispatch_test",
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
                "name": "Reviewer Dispatch Test",
                "login": "reviewer_dispatch_test",
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

    def _create_ready_campaign(self, partner_ids):
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Dispatch Campaign",
                "subject": "Dispatch Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner_ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "dispatch@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.reviewer).action_run_compliance_preflight()
        self.assertEqual(campaign.compliance_state, "ready")
        return campaign

    def test_unfrozen_run_cannot_start_execution(self):
        partner = self._make_partner_with_consent("Unfrozen", "unfrozen.exec@example.com")
        campaign = self._create_ready_campaign(partner.ids)
        run = campaign.current_campaign_run_id
        run.write({"frozen": False})
        with self.assertRaises(UserError):
            run.with_user(self.operator).action_start_execution()

    def test_start_execution_queues_eligible_recipients(self):
        partner = self._make_partner_with_consent("Queue Me", "queue.me@example.com")
        campaign = self._create_ready_campaign(partner.ids)
        run = campaign.current_campaign_run_id

        run.with_user(self.operator).action_start_execution()

        self.assertEqual(run.state, "queued")
        self.assertEqual(campaign.compliance_state, "sending")
        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        self.assertEqual(eligibility.dispatch_state, "queued")

    def test_only_eligible_recipients_are_dispatched(self):
        eligible_partner = self._make_partner_with_consent(
            "Eligible One", "eligible.one@example.com"
        )
        excluded_partner = self.env["res.partner"].create(
            {"name": "Excluded One", "email": "excluded.one@example.com"}
        )
        campaign = self._create_ready_campaign(
            eligible_partner.ids + excluded_partner.ids
        )
        run = campaign.current_campaign_run_id
        run.with_user(self.operator).action_start_execution()

        excluded_decision = run.eligibility_ids.filtered(
            lambda e: e.recipient_res_id == excluded_partner.id
        )
        self.assertEqual(excluded_decision.status, "excluded")
        self.assertEqual(excluded_decision.dispatch_state, "not_queued")

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "test-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        self.assertEqual(mock_send.call_count, 1)
        eligible_decision = run.eligibility_ids.filtered(
            lambda e: e.recipient_res_id == eligible_partner.id
        )
        self.assertEqual(eligible_decision.dispatch_state, "sent")
        self.assertEqual(excluded_decision.dispatch_state, "not_queued")

    def test_dispatch_creates_events(self):
        partner = self._make_partner_with_consent("Events One", "events.one@example.com")
        campaign = self._create_ready_campaign(partner.ids)
        run = campaign.current_campaign_run_id
        run.with_user(self.operator).action_start_execution()

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "test-2",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        event_types = run.event_ids.mapped("event_type")
        self.assertIn("queued", event_types)
        self.assertIn("dispatch_started", event_types)
        self.assertIn("dispatch_recheck_passed", event_types)
        self.assertIn("send_attempted", event_types)
        self.assertIn("send_accepted", event_types)

    def test_sent_is_terminal_no_resend(self):
        partner = self._make_partner_with_consent("Terminal One", "terminal.one@example.com")
        campaign = self._create_ready_campaign(partner.ids)
        run = campaign.current_campaign_run_id
        run.with_user(self.operator).action_start_execution()

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "test-3",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()
            self.assertEqual(mock_send.call_count, 1)

            # a second batch pass must not resend
            run._process_next_dispatch_batch()
            self.assertEqual(mock_send.call_count, 1)
