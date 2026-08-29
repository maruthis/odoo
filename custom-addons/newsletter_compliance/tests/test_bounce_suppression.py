from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services.providers.base_provider import (
    CanonicalDeliveryEvent,
)


@tagged("post_install", "-at_install")
class TestNewsletterBounceSuppression(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Bounce Purpose",
                "code": "BOUNCE_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Bounce Brand",
                "code": "BOUNCE_BRAND",
                "email_from": "bounce@example.com",
                "physical_address": "1 Bounce St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Bounce Test",
                "login": "operator_bounce_test",
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
                "name": "Approver Bounce Test",
                "login": "approver_bounce_test",
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
                "name": "Reviewer Bounce Test",
                "login": "reviewer_bounce_test",
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

    def _create_sent_eligibility(self, email, provider_message_id):
        partner = self.env["res.partner"].create({"name": email, "email": email})
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
                "name": "Bounce Campaign %s" % email,
                "subject": "Bounce Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "bounce@example.com",
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
        return partner, run, eligibility

    def _ingest_bounce(self, provider_message_id, bounce_type, email, event_id, event_timestamp="2026-01-01T11:00:00"):
        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id=event_id,
            provider_message_id=provider_message_id,
            event_type="hard_bounce" if bounce_type == "permanent" else "soft_bounce",
            event_timestamp=event_timestamp,
            email=email,
            bounce_type=bounce_type,
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", event)
        record.process_event()
        return record

    def test_hard_bounce_creates_global_suppression_and_syncs_blacklist(self):
        partner, run, eligibility = self._create_sent_eligibility(
            "hard.bounce@example.com", "msg-hard-1"
        )
        self._ingest_bounce(
            eligibility.provider_message_id, "permanent", "hard.bounce@example.com", "evt-hard-1"
        )

        eligibility.invalidate_recordset()
        self.assertEqual(eligibility.delivery_state, "hard_bounce")

        suppression = self.env["newsletter.suppression.entry"].search(
            [("partner_id", "=", partner.id), ("scope", "=", "global")]
        )
        self.assertTrue(suppression)
        self.assertEqual(suppression.reason_id.code, "HARD_BOUNCE")

        blacklisted = self.env["mail.blacklist"].search(
            [("email", "=", "hard.bounce@example.com")]
        )
        self.assertTrue(blacklisted)

        reputation = self.env["newsletter.delivery.reputation"].search(
            [("email_normalized", "=", "hard.bounce@example.com")]
        )
        self.assertEqual(reputation.hard_bounce_count, 1)
        self.assertEqual(reputation.reputation_state, "suppressed")

    def test_soft_bounce_below_threshold_does_not_suppress(self):
        partner, run, eligibility = self._create_sent_eligibility(
            "soft.below@example.com", "msg-soft-1"
        )
        self._ingest_bounce(
            eligibility.provider_message_id, "transient", "soft.below@example.com", "evt-soft-1"
        )

        suppression = self.env["newsletter.suppression.entry"].search(
            [("partner_id", "=", partner.id), ("scope", "=", "global")]
        )
        self.assertFalse(suppression)

        reputation = self.env["newsletter.delivery.reputation"].search(
            [("email_normalized", "=", "soft.below@example.com")]
        )
        self.assertEqual(reputation.soft_bounce_count, 1)

    def test_soft_bounce_threshold_reached_suppresses(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.soft_bounce_threshold", "3"
        )
        partner, run, eligibility = self._create_sent_eligibility(
            "soft.threshold@example.com", "msg-soft-2"
        )

        for i in range(3):
            # Each "bounce" needs its own dispatched message to correlate
            # against, so re-use the same eligibility's provider_message_id
            # across three separate provider events (as if 3 separate
            # campaign sends bounced for this recipient).
            self._ingest_bounce(
                eligibility.provider_message_id,
                "transient",
                "soft.threshold@example.com",
                "evt-soft-threshold-%d" % i,
                event_timestamp="2026-01-0%dT11:00:00" % (i + 1),
            )

        suppression = self.env["newsletter.suppression.entry"].search(
            [("partner_id", "=", partner.id), ("scope", "=", "global")]
        )
        self.assertTrue(suppression)
        self.assertEqual(suppression.reason_id.code, "SOFT_BOUNCE_LIMIT")

        reputation = self.env["newsletter.delivery.reputation"].search(
            [("email_normalized", "=", "soft.threshold@example.com")]
        )
        self.assertEqual(reputation.soft_bounce_count, 3)

    def test_delivery_resets_soft_bounce_counter(self):
        partner, run, eligibility = self._create_sent_eligibility(
            "soft.reset@example.com", "msg-soft-3"
        )
        self._ingest_bounce(
            eligibility.provider_message_id, "transient", "soft.reset@example.com", "evt-soft-reset-1"
        )
        reputation = self.env["newsletter.delivery.reputation"].search(
            [("email_normalized", "=", "soft.reset@example.com")]
        )
        self.assertEqual(reputation.soft_bounce_count, 1)

        delivered_event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-soft-reset-delivered",
            provider_message_id=eligibility.provider_message_id,
            event_type="delivered",
            event_timestamp="2026-01-02T11:00:00",
            email="soft.reset@example.com",
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", delivered_event)
        record.process_event()

        reputation.invalidate_recordset()
        self.assertEqual(reputation.soft_bounce_count, 0)
