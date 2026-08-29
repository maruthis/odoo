from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services.providers.base_provider import (
    CanonicalDeliveryEvent,
)


@tagged("post_install", "-at_install")
class TestNewsletterDeliveryProcessing(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Delivery Purpose",
                "code": "DELIVERY_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Delivery Brand",
                "code": "DELIVERY_BRAND",
                "email_from": "delivery@example.com",
                "physical_address": "1 Delivery St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Delivery Test",
                "login": "operator_delivery_test",
                "group_ids": [
                    (
                        6, 0,
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
                "name": "Approver Delivery Test",
                "login": "approver_delivery_test",
                "group_ids": [
                    (
                        6, 0,
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
                "name": "Reviewer Delivery Test",
                "login": "reviewer_delivery_test",
                "group_ids": [
                    (
                        6, 0,
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

    def _create_sent_eligibility(self, provider_message_id="msg-delivery-1"):
        partner = self._make_partner_with_consent(
            "Delivery Recipient", "delivery.recipient@example.com"
        )
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Delivery Campaign",
                "subject": "Delivery Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "delivery@example.com",
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
                "provider_message_id": provider_message_id,
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        self.assertEqual(eligibility.provider_message_id, provider_message_id)
        return run, eligibility

    def _ingest_and_process(self, provider_message_id, event_type, event_id):
        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id=event_id,
            provider_message_id=provider_message_id,
            event_type=event_type,
            event_timestamp="2026-01-01T11:00:00",
            email="delivery.recipient@example.com",
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", event)
        record.process_event()
        return record

    def test_delivered_event_updates_recipient_and_outcome(self):
        run, eligibility = self._create_sent_eligibility()
        self._ingest_and_process(eligibility.provider_message_id, "delivered", "evt-delivered-1")

        eligibility.invalidate_recordset()
        self.assertEqual(eligibility.delivery_state, "delivered")
        self.assertEqual(run.current_outcome_id.delivered_count, 1)

    def test_delivered_creates_send_event(self):
        run, eligibility = self._create_sent_eligibility()
        record = self._ingest_and_process(
            eligibility.provider_message_id, "delivered", "evt-delivered-2"
        )
        self.assertEqual(record.processing_state, "processed")
        self.assertTrue(record.send_event_id)
        self.assertEqual(record.send_event_id.event_type, "delivered")

    def test_duplicate_delivered_event_does_not_double_count(self):
        run, eligibility = self._create_sent_eligibility()
        self._ingest_and_process(eligibility.provider_message_id, "delivered", "evt-delivered-dup")
        # Same provider_event_id sent again (provider retry) - must not
        # create a second business event or increment the outcome twice.
        self._ingest_and_process(eligibility.provider_message_id, "delivered", "evt-delivered-dup")

        run.current_outcome_id.invalidate_recordset()
        self.assertEqual(run.current_outcome_id.delivered_count, 1)
