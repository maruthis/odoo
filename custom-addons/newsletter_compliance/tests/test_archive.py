from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterArchive(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Archive Purpose",
                "code": "ARCHIVE_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Archive Brand",
                "code": "ARCHIVE_BRAND",
                "email_from": "archive@example.com",
                "physical_address": "1 Archive St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Archive Test",
                "login": "operator_archive_test",
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
                "name": "Approver Archive Test",
                "login": "approver_archive_test",
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
                "name": "Reviewer Archive Test",
                "login": "reviewer_archive_test",
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

    def _create_completed_campaign(self):
        partner = self._make_partner_with_consent("Archive Recipient", "archive.recipient@example.com")
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Archive Campaign",
                "subject": "Archive Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "archive@example.com",
                "body_html": "<p>Archive content</p>",
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
                "provider_message_id": "archive-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        self.assertEqual(run.state, "archived")
        return campaign, run

    def test_completion_creates_archive(self):
        campaign, run = self._create_completed_campaign()
        self.assertTrue(run.archive_id)

    def test_archive_content_matches_sent_content(self):
        campaign, run = self._create_completed_campaign()
        archive = run.archive_id
        self.assertEqual(archive.subject_snapshot, campaign.subject)
        self.assertEqual(archive.body_html_snapshot, campaign.body_html)
        self.assertEqual(archive.email_from_snapshot, campaign.email_from)

    def test_archive_captures_approval_and_preflight_evidence(self):
        campaign, run = self._create_completed_campaign()
        archive = run.archive_id
        self.assertEqual(archive.content_approved_by_id, campaign.content_approved_by_id)
        self.assertEqual(archive.compliance_approved_by_id, campaign.compliance_approved_by_id)
        self.assertEqual(archive.approval_content_hash, campaign.approval_content_hash)
        self.assertEqual(archive.preflight_result_hash, run.result_hash)

    def test_archive_captures_counts(self):
        campaign, run = self._create_completed_campaign()
        archive = run.archive_id
        self.assertEqual(archive.targeted_count, run.targeted_count)
        self.assertEqual(archive.eligible_count, run.eligible_count)
        self.assertEqual(archive.sent_count, run.sent_count)

    def test_archive_hash_generated_and_verifiable(self):
        campaign, run = self._create_completed_campaign()
        archive = run.archive_id
        self.assertTrue(archive.archive_hash)
        self.assertTrue(archive.verify_integrity())

    def test_locked_archive_cannot_be_modified(self):
        campaign, run = self._create_completed_campaign()
        archive = run.archive_id
        self.assertTrue(archive.locked)
        with self.assertRaises(UserError):
            archive.write({"subject_snapshot": "Tampered Subject"})

    def test_locked_archive_cannot_be_deleted(self):
        campaign, run = self._create_completed_campaign()
        archive = run.archive_id
        with self.assertRaises(UserError):
            archive.unlink()

    def test_outcome_created_alongside_archive(self):
        campaign, run = self._create_completed_campaign()
        outcome = self.env["newsletter.campaign.outcome"].search(
            [("archive_id", "=", run.archive_id.id)]
        )
        self.assertTrue(outcome)
        self.assertFalse(outcome.finalized)

    def test_archive_attachment_copies_actual_file_content(self):
        """R6 gap closure: the archive must hold a real, independent copy
        of each attachment's bytes, not only a hash of content that could
        later be edited/deleted on the source mailing.
        """
        partner = self._make_partner_with_consent(
            "Archive Attachment Recipient", "archive.attachment@example.com"
        )
        source_attachment = self.env["ir.attachment"].create(
            {
                "name": "flyer.txt",
                "datas": __import__("base64").b64encode(b"original flyer content"),
            }
        )
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Archive Attachment Campaign",
                "subject": "Archive Attachment Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "archive@example.com",
                "body_html": "<p>Archive content</p>",
                "attachment_ids": [(6, 0, [source_attachment.id])],
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
                "provider_message_id": "archive-attach-1",
                "error_code": False,
                "error_message": False,
                "retryable": False,
            }
            run._process_next_dispatch_batch()

        archive_attachment = run.archive_id.attachment_ids[:1]
        self.assertTrue(archive_attachment.attachment_copy_id)
        self.assertNotEqual(archive_attachment.attachment_copy_id.id, source_attachment.id)
        self.assertEqual(
            archive_attachment.attachment_copy_id.raw, b"original flyer content"
        )

        # Editing/deleting the source attachment must not affect the copy.
        source_attachment.unlink()
        self.assertTrue(archive_attachment.attachment_copy_id.exists())
        self.assertEqual(
            archive_attachment.attachment_copy_id.raw, b"original flyer content"
        )

    def test_retention_fields_are_writable_on_locked_archive(self):
        """The dead placeholder retention_policy_id/retain_until/legal_hold
        fields from R4 have been replaced with the real retention mixin -
        confirm they can still be stamped after the archive locks, since
        that write must not trip the immutability guard.
        """
        campaign, run = self._create_completed_campaign()
        archive = run.archive_id
        policy = self.env["newsletter.retention.policy"].create(
            {
                "name": "Archive Retention Test Policy",
                "code": "ARCHIVE_RETENTION_TEST",
                "data_category": "campaign_archive",
                "retention_period_days": 365,
                "expiry_action": "review",
            }
        )
        archive.write({"retention_policy_id": policy.id, "legal_hold": True})
        self.assertEqual(archive.retention_policy_id, policy)
        self.assertTrue(archive.legal_hold)
        with self.assertRaises(UserError):
            archive.write({"subject_snapshot": "Still Immutable"})

    def test_campaign_run_retention_mixin_fields_are_real(self):
        """R6 gap closure: campaign_run's retention_policy_id/retain_until/
        legal_hold used to be dead Char/Date/Boolean fields unrelated to
        the actual retention mixin - confirm the real Many2one/Datetime
        typed fields work now.
        """
        _campaign, run = self._create_completed_campaign()
        policy = self.env["newsletter.retention.policy"].create(
            {
                "name": "Campaign Run Retention Test Policy",
                "code": "CAMPAIGN_RUN_RETENTION_TEST",
                "data_category": "campaign_run",
                "retention_period_days": 365,
                "expiry_action": "review",
            }
        )
        run.write({"retention_policy_id": policy.id, "legal_hold": True})
        self.assertEqual(run.retention_policy_id, policy)
        self.assertTrue(run.legal_hold)
