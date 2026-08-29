from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import reconciliation_service


@tagged("post_install", "-at_install")
class TestNewsletterReconciliation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Reconciliation Purpose",
                "code": "RECONCILIATION_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Reconciliation Brand",
                "code": "RECONCILIATION_BRAND",
                "email_from": "reconcile@example.com",
                "physical_address": "1 Reconcile St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Reconciliation Test",
                "login": "operator_reconciliation_test",
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
                "name": "Approver Reconciliation Test",
                "login": "approver_reconciliation_test",
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
                "name": "Reviewer Reconciliation Test",
                "login": "reviewer_reconciliation_test",
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

    def test_service_reconciles_invariant(self):
        counts = {"sent": 8, "failed": 1, "blocked": 1, "cancelled": 0}
        self.assertTrue(reconciliation_service.reconciles(10, counts))
        self.assertFalse(reconciliation_service.reconciles(11, counts))

    def test_service_is_complete_requires_no_pending(self):
        counts = {"sent": 5, "queued": 5}
        self.assertFalse(reconciliation_service.is_complete(10, counts))
        counts = {"sent": 10, "queued": 0, "processing": 0, "retry_pending": 0}
        self.assertTrue(reconciliation_service.is_complete(10, counts))

    def test_service_classification(self):
        self.assertEqual(
            reconciliation_service.classify_completion({"failed": 0, "sent": 10}), "completed"
        )
        self.assertEqual(
            reconciliation_service.classify_completion({"failed": 2, "sent": 8}),
            "completed_with_errors",
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

    def _create_queued_run(self, partner_ids):
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Reconciliation Campaign",
                "subject": "Reconciliation Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner_ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "reconcile@example.com",
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

    def test_all_successful_completes_clean(self):
        partner = self._make_partner_with_consent("Recon Clean", "recon.clean@example.com")
        campaign, run = self._create_queued_run(partner.ids)

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "recon-clean-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        # a clean completion is immediately archived (spec section 42:
        # archive as soon as dispatch completes), so "completed" is a
        # transient state - failed_count/sent_count are what distinguish
        # a clean run from one "with errors" once archived.
        self.assertEqual(run.state, "archived")
        self.assertEqual(campaign.compliance_state, "completed")
        self.assertEqual(run.sent_count, 1)
        self.assertEqual(run.failed_count, 0)

    def test_final_failure_completes_with_errors(self):
        partner = self._make_partner_with_consent("Recon Errors", "recon.errors@example.com")
        campaign, run = self._create_queued_run(partner.ids)

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

        # also auto-archived immediately, but the failure is still on record
        self.assertEqual(run.state, "archived")
        self.assertEqual(run.failed_count, 1)

    def test_eligible_equals_terminal_states(self):
        partner_a = self._make_partner_with_consent("Recon A", "recon.a@example.com")
        partner_b = self._make_partner_with_consent("Recon B", "recon.b@example.com")
        campaign, run = self._create_queued_run(partner_a.ids + partner_b.ids)

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "recon-multi-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        eligible = run.eligibility_ids.filtered(lambda e: e.status == "eligible")
        terminal = eligible.filtered(
            lambda e: e.dispatch_state in ("sent", "failed", "blocked", "cancelled")
        )
        self.assertEqual(len(terminal), len(eligible))
        self.assertEqual(run.state, "archived")
