from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import audit_export_service, privacy_discovery_service


@tagged("post_install", "-at_install")
class TestNewsletterAuditExport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Export Purpose",
                "code": "EXPORT_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Export Brand",
                "code": "EXPORT_BRAND",
                "email_from": "export@example.com",
                "physical_address": "1 Export St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Export Test",
                "login": "operator_export_test",
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
                "name": "Approver Export Test",
                "login": "approver_export_test",
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
                "name": "Reviewer Export Test",
                "login": "reviewer_export_test",
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
                "name": "Export Campaign %s" % email,
                "subject": "Export Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "export@example.com",
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
                "provider_message_id": "export-msg-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        return partner, run

    def test_build_campaign_package_masks_email_by_default(self):
        _partner, run = self._create_run_with_events("mask.export@example.com")
        package, file_hash = audit_export_service.build_campaign_package(self.env, run, masked=True)
        self.assertTrue(file_hash)
        self.assertIn("email_from", package["campaign"])
        self.assertNotEqual(package["campaign"]["email_from"], "export@example.com")
        self.assertTrue(package["campaign"]["email_from"].endswith("@example.com"))

    def test_build_campaign_package_unmasked_shows_real_email(self):
        _partner, run = self._create_run_with_events("unmask.export@example.com")
        package, _file_hash = audit_export_service.build_campaign_package(self.env, run, masked=False)
        self.assertEqual(package["campaign"]["email_from"], "export@example.com")

    def test_campaign_package_hash_is_stable_for_same_data(self):
        _partner, run = self._create_run_with_events("stable.hash@example.com")
        _pkg1, hash1 = audit_export_service.build_campaign_package(self.env, run, masked=True)
        _pkg2, hash2 = audit_export_service.build_campaign_package(self.env, run, masked=True)
        self.assertEqual(hash1, hash2)

    def test_action_generate_campaign_package_creates_attachment(self):
        _partner, run = self._create_run_with_events("attach.export@example.com")
        export = self.env["newsletter.audit.export"].create(
            {"export_type": "campaign", "campaign_run_id": run.id, "masked": True}
        )
        export.action_generate_campaign_package()
        self.assertTrue(export.attachment_id)
        self.assertTrue(export.file_hash)
        self.assertEqual(export.record_count, 1)

    def test_recipient_package_masks_eligibility_email(self):
        partner, _run = self._create_run_with_events("recipient.export@example.com")
        discovery = privacy_discovery_service.discover(self.env, partner=partner)
        package, _file_hash = audit_export_service.build_recipient_package(
            self.env, discovery["manifest"], masked=True
        )
        self.assertTrue(package["eligibility_decisions"])
        for decision in package["eligibility_decisions"]:
            self.assertNotEqual(decision["email"], "recipient.export@example.com")

    def test_expired_export_removes_attachment_but_keeps_record(self):
        _partner, run = self._create_run_with_events("expire.export@example.com")
        export = self.env["newsletter.audit.export"].create(
            {"export_type": "campaign", "campaign_run_id": run.id, "masked": True}
        )
        export.action_generate_campaign_package()
        self.assertTrue(export.attachment_id)

        export.write({"expires_at": "2020-01-01 00:00:00"})
        self.env["newsletter.audit.export"]._cron_expire_audit_exports()

        self.assertTrue(export.exists())
        self.assertFalse(export.attachment_id)
        self.assertTrue(export.file_hash)
