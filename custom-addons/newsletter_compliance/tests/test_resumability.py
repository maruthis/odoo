from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterResumability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Resumability Purpose",
                "code": "RESUMABILITY_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Resumability Brand",
                "code": "RESUMABILITY_BRAND",
                "email_from": "resume@example.com",
                "physical_address": "1 Resume St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Resumability Test",
                "login": "operator_resumability_test",
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
                "name": "Approver Resumability Test",
                "login": "approver_resumability_test",
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
                "name": "Reviewer Resumability Test",
                "login": "reviewer_resumability_test",
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

    def _make_partners_with_consent(self, count):
        partners = self.env["res.partner"]
        for i in range(count):
            partner = self.env["res.partner"].create(
                {"name": f"Resumable {i}", "email": f"resumable.{i}@example.com"}
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

    def test_interrupted_batch_resumes_without_resending(self):
        partners = self._make_partners_with_consent(5)
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Resumability Campaign",
                "subject": "Resumability Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partners.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "resume@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.reviewer).action_run_compliance_preflight()
        run = campaign.current_campaign_run_id
        self.assertEqual(run.eligible_count, 5)

        # small batch size so one worker pass only handles part of the run,
        # simulating an interruption/resumption cycle
        run.write({"execution_batch_size": 2})
        run.with_user(self.operator).action_start_execution()

        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "resumable-batch-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()  # handles 2 of 5

        self.assertEqual(mock_send.call_count, 2)
        sent_after_first_batch = run.eligibility_ids.filtered(
            lambda e: e.dispatch_state == "sent"
        )
        self.assertEqual(len(sent_after_first_batch), 2)
        first_batch_ids = set(sent_after_first_batch.ids)
        self.assertEqual(run.state, "partially_completed")

        # "restart the worker" - process remaining batches
        with patch(
            "odoo.addons.newsletter_compliance.services.dispatch_service.send_recipient"
        ) as mock_send:
            mock_send.return_value = {
                "accepted": True,
                "provider_message_id": "resumable-batch-2",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()  # handles next 2
            run._process_next_dispatch_batch()  # handles final 1

        # the recipients sent in the first batch were never re-submitted
        self.assertEqual(mock_send.call_count, 3)

        all_sent = run.eligibility_ids.filtered(lambda e: e.dispatch_state == "sent")
        self.assertEqual(len(all_sent), 5)
        self.assertTrue(first_batch_ids.issubset(set(all_sent.ids)))

        self.assertEqual(run.state, "archived")
        self.assertEqual(run.sent_count, 5)
