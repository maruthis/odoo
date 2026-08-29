from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services.providers.base_provider import (
    CanonicalDeliveryEvent,
)


@tagged("post_install", "-at_install")
class TestNewsletterOutcomeAndAlerts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Outcome Purpose",
                "code": "OUTCOME_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Outcome Brand",
                "code": "OUTCOME_BRAND",
                "email_from": "outcome@example.com",
                "physical_address": "1 Outcome St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Outcome Test",
                "login": "operator_outcome_test",
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
                "name": "Approver Outcome Test",
                "login": "approver_outcome_test",
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
                "name": "Reviewer Outcome Test",
                "login": "reviewer_outcome_test",
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

    def _make_partners_with_consent(self, count):
        partners = self.env["res.partner"]
        for i in range(count):
            partner = self.env["res.partner"].create(
                {"name": f"Outcome {i}", "email": f"outcome.{i}@example.com"}
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
            partners |= partner
        return partners

    def _start_execution(self, partners):
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Outcome Campaign",
                "subject": "Outcome Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partners.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "outcome@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.reviewer).action_run_compliance_preflight()
        run = campaign.current_campaign_run_id
        run.with_user(self.operator).action_start_execution()
        return campaign, run

    def test_outcome_created_at_execution_start(self):
        partners = self._make_partners_with_consent(1)
        campaign, run = self._start_execution(partners)
        self.assertTrue(run.current_outcome_id)
        self.assertFalse(run.current_outcome_id.finalized)

    def test_outcome_rates_calculate_correctly(self):
        outcome = self.env["newsletter.campaign.outcome"].create(
            {
                "campaign_run_id": self.env["newsletter.campaign.run"].search([], limit=1).id
                or self._make_dummy_run().id,
                "mailing_id": self.env["mailing.mailing"].search([], limit=1).id,
                "sent_count": 100,
                "delivered_count": 90,
                "soft_bounced_count": 5,
                "hard_bounced_count": 3,
                "complained_count": 1,
            }
        )
        self.assertAlmostEqual(outcome.delivery_rate, 0.9)
        self.assertAlmostEqual(outcome.bounce_rate, 0.08)
        self.assertAlmostEqual(outcome.hard_bounce_rate, 0.03)
        self.assertAlmostEqual(outcome.complaint_rate, 0.01)

    def _make_dummy_run(self):
        partners = self._make_partners_with_consent(1)
        _campaign, run = self._start_execution(partners)
        return run

    def test_bounce_threshold_raises_alert_and_dedupes(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.bounce_warning_rate", "0.1"
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.bounce_critical_rate", "0.9"
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.auto_suspend_on_critical", "False"
        )

        partners = self._make_partners_with_consent(2)
        campaign, run = self._start_execution(partners)

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.side_effect = [
                {
                    "accepted": True, "provider_message_id": "msg-alert-1",
                    "error_code": False, "error_message": False, "retryable": False,
                },
                {
                    "accepted": True, "provider_message_id": "msg-alert-2",
                    "error_code": False, "error_message": False, "retryable": False,
                },
            ]
            run._process_next_dispatch_batch()

        eligible = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        target = eligible[0]

        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-alert-bounce-1",
            provider_message_id=target.provider_message_id,
            event_type="hard_bounce",
            event_timestamp="2026-01-01T12:00:00",
            email=target.email_normalized,
            bounce_type="permanent",
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", event)
        record.process_event()

        alerts = self.env["newsletter.compliance.alert"].search(
            [("campaign_run_id", "=", run.id), ("alert_type", "=", "bounce_threshold")]
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts.status, "open")

        # a second bounce on the same run must update the existing alert,
        # not create a duplicate
        target2 = eligible[1]
        event2 = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-alert-bounce-2",
            provider_message_id=target2.provider_message_id,
            event_type="hard_bounce",
            event_timestamp="2026-01-01T12:05:00",
            email=target2.email_normalized,
            bounce_type="permanent",
        )
        record2, _created2 = self.env["newsletter.provider.event"].ingest("generic", event2)
        record2.process_event()

        alerts_after = self.env["newsletter.compliance.alert"].search(
            [("campaign_run_id", "=", run.id), ("alert_type", "=", "bounce_threshold")]
        )
        self.assertEqual(len(alerts_after), 1)

    def test_alert_can_be_acknowledged_and_resolved(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.bounce_warning_rate", "0.1"
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.bounce_critical_rate", "0.9"
        )

        partners = self._make_partners_with_consent(1)
        campaign, run = self._start_execution(partners)

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True, "provider_message_id": "msg-ack-1",
                "error_code": False, "error_message": False, "retryable": False,
            }
            run._process_next_dispatch_batch()

        eligible = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-ack-1",
            provider_message_id=eligible.provider_message_id,
            event_type="hard_bounce",
            event_timestamp="2026-01-01T12:00:00",
            email=eligible.email_normalized,
            bounce_type="permanent",
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", event)
        record.process_event()

        alert = self.env["newsletter.compliance.alert"].search(
            [("campaign_run_id", "=", run.id)], limit=1
        )
        self.assertEqual(alert.status, "open")
        alert.action_acknowledge()
        self.assertEqual(alert.status, "acknowledged")
        alert.action_resolve(notes="Investigated, root cause fixed.")
        self.assertEqual(alert.status, "resolved")
        self.assertEqual(alert.resolution_notes, "Investigated, root cause fixed.")

    def test_finalize_locks_outcome_and_late_event_becomes_adjustment(self):
        partners = self._make_partners_with_consent(1)
        campaign, run = self._start_execution(partners)

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True, "provider_message_id": "msg-finalize-1",
                "error_code": False, "error_message": False, "retryable": False,
            }
            run._process_next_dispatch_batch()

        outcome = run.current_outcome_id
        outcome.action_finalize()
        self.assertTrue(outcome.finalized)
        self.assertTrue(outcome.outcome_hash)

        eligible = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        late_event = CanonicalDeliveryEvent(
            provider="generic",
            provider_event_id="evt-late-1",
            provider_message_id=eligible.provider_message_id,
            event_type="delivered",
            event_timestamp="2026-01-05T12:00:00",
            email=eligible.email_normalized,
        )
        record, _created = self.env["newsletter.provider.event"].ingest("generic", late_event)
        record.process_event()

        outcome.invalidate_recordset()
        self.assertEqual(outcome.delivered_count, 0)
        self.assertEqual(len(outcome.adjustment_ids), 1)
        self.assertEqual(outcome.adjustment_ids.event_type, "delivered")
