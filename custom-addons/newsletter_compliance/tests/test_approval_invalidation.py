from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterApprovalInvalidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Corporate Newsletter R2",
                "code": "CORPORATE_R2",
                "privacy_notice_version": "v1",
            }
        )
        cls.other_purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Promotions R2",
                "code": "PROMOTIONS_R2",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Corporate",
                "code": "CORPORATE_BRAND",
                "email_from": "corporate@example.com",
                "physical_address": "1 Corporate Plaza, Springfield",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )

    def _create_approved_campaign(self):
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "August Newsletter",
                "subject": "August Healthcare Insights",
                "mailing_type": "mail",
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "corporate@example.com",
                "body_html": "<p>Original content</p>",
                "mailing_domain": "[]",
            }
        )
        campaign.action_submit_content_review()
        content_approver = self.env["res.users"].create(
            {
                "name": "Approver Inv Test",
                "login": "approver_inv_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("mass_mailing.group_mass_mailing_user").id,
                            self.env.ref(
                                "newsletter_compliance.group_newsletter_content_approver"
                            ).id,
                        ],
                    )
                ],
            }
        )
        compliance_reviewer = self.env["res.users"].create(
            {
                "name": "Reviewer Inv Test",
                "login": "reviewer_inv_test",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("mass_mailing.group_mass_mailing_user").id,
                            self.env.ref(
                                "newsletter_compliance.group_newsletter_compliance_reviewer"
                            ).id,
                        ],
                    )
                ],
            }
        )
        campaign.with_user(content_approver).action_approve_content()
        campaign.with_user(compliance_reviewer).action_approve_compliance()
        self.assertEqual(campaign.compliance_state, "preflight_required")
        return campaign

    def test_subject_change_invalidates_approval(self):
        campaign = self._create_approved_campaign()
        campaign.write({"subject": "URGENT - BUY NOW!!!"})
        self.assertEqual(campaign.compliance_state, "draft")
        self.assertFalse(campaign.content_approved_by_id)
        self.assertFalse(campaign.compliance_approved_by_id)
        self.assertEqual(campaign.preflight_status, "not_run")

    def test_body_change_invalidates_approval(self):
        campaign = self._create_approved_campaign()
        campaign.write({"body_html": "<p>Completely different content</p>"})
        self.assertEqual(campaign.compliance_state, "draft")

    def test_consent_purpose_change_invalidates_approval(self):
        campaign = self._create_approved_campaign()
        campaign.write({"consent_purpose_id": self.other_purpose.id})
        self.assertEqual(campaign.compliance_state, "draft")

    def test_email_from_change_invalidates_approval(self):
        campaign = self._create_approved_campaign()
        campaign.write({"email_from": "someone-else@example.com"})
        self.assertEqual(campaign.compliance_state, "draft")

    def test_recipient_domain_change_invalidates_approval(self):
        campaign = self._create_approved_campaign()
        campaign.write({"mailing_domain": "[('email', 'like', 'example.com')]"})
        self.assertEqual(campaign.compliance_state, "draft")

    def test_invalidation_recorded_in_chatter(self):
        campaign = self._create_approved_campaign()
        campaign.write({"subject": "Changed Subject"})
        messages = campaign.message_ids.mapped("body")
        self.assertTrue(
            any("invalidated" in (body or "").lower() for body in messages)
        )

    def test_unrelated_field_change_does_not_invalidate(self):
        campaign = self._create_approved_campaign()
        campaign.write({"compliance_owner_id": self.env.user.id})
        self.assertEqual(campaign.compliance_state, "preflight_required")
        self.assertTrue(campaign.content_approved_by_id)
        self.assertTrue(campaign.compliance_approved_by_id)

    def test_copy_does_not_inherit_approval(self):
        campaign = self._create_approved_campaign()
        original_id = campaign.compliance_campaign_id

        copy = campaign.copy()

        self.assertNotEqual(copy.compliance_campaign_id, original_id)
        self.assertTrue(copy.compliance_campaign_id)
        self.assertEqual(copy.compliance_state, "draft")
        self.assertFalse(copy.content_approved_by_id)
        self.assertFalse(copy.compliance_approved_by_id)
        self.assertEqual(copy.preflight_status, "not_run")
        self.assertFalse(copy.approval_history_ids)
