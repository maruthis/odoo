from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services.providers.base_provider import (
    CanonicalDeliveryEvent,
)


@tagged("post_install", "-at_install")
class TestNewsletterComplaint(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Complaint Purpose",
                "code": "COMPLAINT_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Complaint Brand",
                "code": "COMPLAINT_BRAND",
                "email_from": "complaint@example.com",
                "physical_address": "1 Complaint St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Complaint Test",
                "login": "operator_complaint_test",
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
                "name": "Approver Complaint Test",
                "login": "approver_complaint_test",
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
                "name": "Reviewer Complaint Test",
                "login": "reviewer_complaint_test",
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

    def _create_sent_eligibility(self):
        partner = self.env["res.partner"].create(
            {"name": "Complainer", "email": "complainer@example.com"}
        )
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
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Complaint Campaign",
                "subject": "Complaint Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "complaint@example.com",
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
                "provider_message_id": "msg-complaint-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        eligibility = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        return partner, run, eligibility

    def test_complaint_creates_global_suppression_synced_to_blacklist(self):
        partner, run, eligibility = self._create_sent_eligibility()

        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-complaint-1",
            provider_message_id=eligibility.provider_message_id,
            event_type="complaint",
            event_timestamp="2026-01-01T12:00:00",
            email="complainer@example.com",
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", event)
        record.process_event()

        eligibility.invalidate_recordset()
        self.assertEqual(eligibility.delivery_state, "complaint")

        suppression = self.env["newsletter.suppression.entry"].search(
            [("partner_id", "=", partner.id), ("scope", "=", "global")]
        )
        self.assertTrue(suppression)
        self.assertEqual(suppression.reason_id.code, "COMPLAINT")
        self.assertFalse(suppression.reason_id.allow_reinstatement)

        blacklisted = self.env["mail.blacklist"].search(
            [("email", "=", "complainer@example.com")]
        )
        self.assertTrue(blacklisted)

        reputation = self.env["newsletter.delivery.reputation"].search(
            [("email_normalized", "=", "complainer@example.com")]
        )
        self.assertEqual(reputation.complaint_count, 1)

    def test_complaint_suppression_cannot_be_reinstated_by_ordinary_reviewer(self):
        partner, run, eligibility = self._create_sent_eligibility()

        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-complaint-2",
            provider_message_id=eligibility.provider_message_id,
            event_type="complaint",
            event_timestamp="2026-01-01T12:00:00",
            email="complainer@example.com",
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", event)
        record.process_event()

        suppression = self.env["newsletter.suppression.entry"].search(
            [("partner_id", "=", partner.id), ("scope", "=", "global")]
        )
        self.assertFalse(suppression.reason_id.allow_reinstatement)
