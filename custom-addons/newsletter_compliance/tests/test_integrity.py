from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import integrity_service


@tagged("post_install", "-at_install")
class TestNewsletterIntegrity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Integrity Purpose",
                "code": "INTEGRITY_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Integrity Brand",
                "code": "INTEGRITY_BRAND",
                "email_from": "integrity@example.com",
                "physical_address": "1 Integrity St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Integrity Test",
                "login": "operator_integrity_test",
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
                "name": "Approver Integrity Test",
                "login": "approver_integrity_test",
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
                "name": "Reviewer Integrity Test",
                "login": "reviewer_integrity_test",
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

    def _create_run_with_events(self, email):
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
                "name": "Integrity Campaign %s" % email,
                "subject": "Integrity Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "integrity@example.com",
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
                "provider_message_id": "integrity-msg-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        return run

    def test_verify_run_integrity_passes_for_untampered_run(self):
        run = self._create_run_with_events("intact.integrity@example.com")
        result = integrity_service.verify_run_integrity(run)
        self.assertTrue(result["events_ok"])
        self.assertTrue(result["archive_ok"])
        self.assertTrue(result["all_ok"])

    def test_verify_run_integrity_detects_tampered_outcome(self):
        run = self._create_run_with_events("tampered.integrity@example.com")
        outcome = run.current_outcome_id
        outcome.action_finalize()
        self.assertTrue(outcome.verify_integrity())

        # Simulate tampering by rewriting a locked field directly in the
        # DB, bypassing the model's write() guard (as a compromised
        # actor with direct SQL access might) - the stored hash should
        # then no longer match the row's actual data.
        # Flush any pending ORM-cached writes first, otherwise Odoo's
        # implicit pre-read flush would silently overwrite our raw SQL
        # tampering with the still-cached (pre-tamper) value on the next
        # ORM field access - the same ordering hazard as the R4 dispatch
        # batch-locking bug.
        outcome.flush_recordset()
        self.env.cr.execute(
            "UPDATE newsletter_campaign_outcome SET sent_count = sent_count + 100 WHERE id = %s",
            (outcome.id,),
        )
        outcome.invalidate_recordset()
        self.assertFalse(outcome.verify_integrity())

        result = integrity_service.verify_run_integrity(run)
        self.assertFalse(result["outcome_ok"])
        self.assertFalse(result["all_ok"])

    def test_verify_run_integrity_creates_alert_on_failure(self):
        run = self._create_run_with_events("alert.integrity@example.com")
        outcome = run.current_outcome_id
        outcome.action_finalize()

        outcome.flush_recordset()
        self.env.cr.execute(
            "UPDATE newsletter_campaign_outcome SET hard_bounced_count = hard_bounced_count + 5 WHERE id = %s",
            (outcome.id,),
        )
        outcome.invalidate_recordset()

        integrity_service.verify_run_integrity(run, raise_alert_on_failure=True)

        alert = self.env["newsletter.compliance.alert"].search(
            [("alert_type", "=", "archive_integrity_failure"), ("campaign_run_id", "=", run.id)]
        )
        self.assertTrue(alert)

    def test_archive_verify_integrity_method_exists_and_passes(self):
        run = self._create_run_with_events("archive.integrity@example.com")
        self.assertTrue(run.archive_id)
        self.assertTrue(run.archive_id.verify_integrity())
