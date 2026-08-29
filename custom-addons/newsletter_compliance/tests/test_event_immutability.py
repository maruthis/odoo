from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterEventImmutability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Event Purpose",
                "code": "EVENT_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Event Brand",
                "code": "EVENT_BRAND",
                "email_from": "events@example.com",
                "physical_address": "1 Event St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Event Test",
                "login": "operator_event_test",
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
        cls.plain_user = cls.env["res.users"].create(
            {
                "name": "Plain Event Test",
                "login": "plain_event_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref(
                                "newsletter_compliance.group_newsletter_compliance_user"
                            ).id,
                        ],
                    )
                ],
            }
        )
        cls.approver = cls.env["res.users"].create(
            {
                "name": "Approver Event Test",
                "login": "approver_event_test",
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
                "name": "Reviewer Event Test",
                "login": "reviewer_event_test",
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

    def _create_run_with_events(self):
        partner = self._make_partner_with_consent("Event Recipient", "event.recipient@example.com")
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Event Campaign",
                "subject": "Event Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "events@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.reviewer).action_run_compliance_preflight()
        run = campaign.current_campaign_run_id
        run.with_user(self.operator).action_start_execution()

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "immutability-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        return run

    def test_events_cannot_be_written(self):
        run = self._create_run_with_events()
        event = run.event_ids[:1]
        with self.assertRaises(UserError):
            event.write({"error_message": "tampered"})

    def test_retention_fields_writable_but_content_still_immutable(self):
        run = self._create_run_with_events()
        event = run.event_ids[:1]
        policy = self.env["newsletter.retention.policy"].create(
            {
                "name": "Send Event Retention Test Policy",
                "code": "SEND_EVENT_RETENTION_TEST",
                "data_category": "send_event",
                "retention_period_days": 365,
                "expiry_action": "review",
            }
        )
        event.write({"retention_policy_id": policy.id, "legal_hold": True})
        self.assertEqual(event.retention_policy_id, policy)
        self.assertTrue(event.legal_hold)
        with self.assertRaises(UserError):
            event.write({"error_message": "tampered"})

    def test_events_cannot_be_deleted(self):
        run = self._create_run_with_events()
        event = run.event_ids[:1]
        with self.assertRaises(UserError):
            event.unlink()

    def test_event_hash_chain_validates(self):
        run = self._create_run_with_events()
        self.assertTrue(run.event_ids.verify_integrity())

    def test_ordinary_user_cannot_create_event_directly(self):
        run = self._create_run_with_events()
        eligibility = run.eligibility_ids[:1]
        with self.assertRaises(AccessError):
            self.env["newsletter.send.event"].with_user(self.plain_user).create(
                {
                    "campaign_run_id": run.id,
                    "mailing_id": run.mailing_id.id,
                    "eligibility_id": eligibility.id,
                    "event_type": "send_accepted",
                }
            )

    def test_duplicate_provider_event_is_idempotent(self):
        run = self._create_run_with_events()
        eligibility = run.eligibility_ids[:1]
        self.env["newsletter.send.event"].sudo().create(
            {
                "campaign_run_id": run.id,
                "mailing_id": run.mailing_id.id,
                "eligibility_id": eligibility.id,
                "event_type": "delivered",
                "source": "provider",
                "provider_event_id": "provider-evt-123",
            }
        )
        with self.assertRaises(Exception):
            self.env["newsletter.send.event"].sudo().create(
                {
                    "campaign_run_id": run.id,
                    "mailing_id": run.mailing_id.id,
                    "eligibility_id": eligibility.id,
                    "event_type": "delivered",
                    "source": "provider",
                    "provider_event_id": "provider-evt-123",
                }
            )
