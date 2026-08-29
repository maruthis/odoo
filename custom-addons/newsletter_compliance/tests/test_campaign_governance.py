from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterCampaignGovernance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Healthcare Newsletter",
                "code": "HEALTHCARE_R2",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Healthcare",
                "code": "HEALTHCARE_BRAND",
                "email_from": "healthcare@example.com",
                "physical_address": "123 Main St, Springfield",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )

        cls.base_group_user = cls.env.ref("base.group_user")
        cls.mass_mailing_group = cls.env.ref("mass_mailing.group_mass_mailing_user")
        cls.group_author = cls.env.ref("newsletter_compliance.group_newsletter_author")
        cls.group_content_approver = cls.env.ref(
            "newsletter_compliance.group_newsletter_content_approver"
        )
        cls.group_compliance_reviewer = cls.env.ref(
            "newsletter_compliance.group_newsletter_compliance_reviewer"
        )
        cls.group_admin = cls.env.ref(
            "newsletter_compliance.group_newsletter_compliance_admin"
        )

        cls.author_user = cls.env["res.users"].create(
            {
                "name": "Newsletter Author",
                "login": "newsletter_author_test",
                "group_ids": [
                    (6, 0, [cls.base_group_user.id, cls.mass_mailing_group.id, cls.group_author.id])
                ],
            }
        )
        cls.content_approver_user = cls.env["res.users"].create(
            {
                "name": "Content Approver",
                "login": "content_approver_test",
                "group_ids": [
                    (6, 0, [cls.base_group_user.id, cls.mass_mailing_group.id, cls.group_content_approver.id])
                ],
            }
        )
        cls.compliance_reviewer_user = cls.env["res.users"].create(
            {
                "name": "Compliance Reviewer R2",
                "login": "compliance_reviewer_r2_test",
                "group_ids": [
                    (6, 0, [cls.base_group_user.id, cls.mass_mailing_group.id, cls.group_compliance_reviewer.id])
                ],
            }
        )

    def _create_campaign(self, **extra):
        vals = {
            "name": "Healthcare Monthly Newsletter",
            "subject": "August Healthcare Insights",
            "mailing_type": "mail",
            "brand_id": self.brand.id,
            "consent_purpose_id": self.purpose.id,
            "email_from": "healthcare@example.com",
            "body_html": "<p>Newsletter content</p>",
            "mailing_domain": "[]",
            "business_owner_id": self.author_user.id,
        }
        vals.update(extra)
        return self.env["mailing.mailing"].with_user(self.author_user).create(vals)

    def test_campaign_compliance_id_generated(self):
        campaign = self._create_campaign()
        self.assertTrue(campaign.compliance_campaign_id)
        self.assertTrue(campaign.compliance_campaign_id.startswith("CMP-"))
        self.assertEqual(campaign.compliance_state, "draft")
        self.assertEqual(campaign.business_owner_id, self.author_user)

    def test_submit_without_consent_purpose_blocked(self):
        campaign = self._create_campaign()
        campaign.with_context(skip_compliance_invalidation=True).write(
            {"consent_purpose_id": False}
        )
        with self.assertRaises(ValidationError):
            campaign.action_submit_content_review()

    def test_submit_without_recipients_blocked(self):
        campaign = self._create_campaign(mailing_domain=False)
        with self.assertRaises(ValidationError):
            campaign.action_submit_content_review()

    def test_valid_campaign_moves_to_content_review(self):
        campaign = self._create_campaign()
        campaign.action_submit_content_review()
        self.assertEqual(campaign.compliance_state, "content_review")

    def test_author_cannot_approve_own_campaign(self):
        campaign = self._create_campaign()
        campaign.action_submit_content_review()
        author_as_approver = campaign.with_user(self.author_user)
        # give the author content-approver rights to isolate the
        # ownership check from the group check
        self.author_user.group_ids = [(4, self.group_content_approver.id)]
        with self.assertRaises(UserError):
            author_as_approver.action_approve_content()

    def test_unauthorized_user_cannot_approve_content(self):
        campaign = self._create_campaign()
        campaign.action_submit_content_review()
        with self.assertRaises(UserError):
            campaign.with_user(self.compliance_reviewer_user).action_approve_content()

    def test_content_approver_can_approve(self):
        campaign = self._create_campaign()
        campaign.action_submit_content_review()
        campaign.with_user(self.content_approver_user).action_approve_content()
        self.assertEqual(campaign.compliance_state, "compliance_review")
        self.assertEqual(campaign.content_approved_by_id, self.content_approver_user)
        self.assertEqual(campaign.approval_version, 1)

    def test_compliance_reviewer_can_approve(self):
        campaign = self._create_campaign()
        campaign.action_submit_content_review()
        campaign.with_user(self.content_approver_user).action_approve_content()
        campaign.with_user(self.compliance_reviewer_user).action_approve_compliance()
        self.assertEqual(campaign.compliance_state, "preflight_required")
        self.assertEqual(
            campaign.compliance_approved_by_id, self.compliance_reviewer_user
        )
        self.assertEqual(campaign.preflight_status, "required")

    def test_rejection_requires_reason(self):
        campaign = self._create_campaign()
        campaign.action_submit_content_review()
        with self.assertRaises(UserError):
            campaign.with_user(self.content_approver_user).action_reject(reason=False)

    def test_reject_returns_to_draft(self):
        campaign = self._create_campaign()
        campaign.action_submit_content_review()
        campaign.with_user(self.content_approver_user).action_reject(
            reason="Needs rework", return_to="draft"
        )
        self.assertEqual(campaign.compliance_state, "draft")
        self.assertEqual(campaign.rejected_by_id, self.content_approver_user)
        self.assertTrue(campaign.rejection_reason)

    def test_cancel_campaign_requires_reason(self):
        campaign = self._create_campaign()
        with self.assertRaises(UserError):
            campaign.with_user(self.author_user).action_cancel_campaign(reason=False)

    def test_owner_can_cancel_campaign(self):
        campaign = self._create_campaign()
        campaign.with_user(self.author_user).action_cancel_campaign(
            reason="No longer needed"
        )
        self.assertEqual(campaign.compliance_state, "cancelled")
        self.assertEqual(campaign.cancelled_by_id, self.author_user)

    def test_non_owner_non_admin_cannot_cancel(self):
        campaign = self._create_campaign()
        with self.assertRaises(UserError):
            campaign.with_user(self.compliance_reviewer_user).action_cancel_campaign(
                reason="Trying to cancel someone else's campaign"
            )

    def test_company_isolated_brands(self):
        other_company = self.env["res.company"].create({"name": "Other Brand Co"})
        other_brand = self.env["newsletter.campaign.brand"].create(
            {
                "name": "Other Co Brand",
                "code": "OTHERCOBRAND",
                "company_id": other_company.id,
            }
        )
        # ir.rule is bypassed entirely for the superuser (TransactionCase's
        # default env.user), so this must run as a real, non-superuser user
        # for the company rule to actually be exercised.
        visible = self.env["newsletter.campaign.brand"].with_user(
            self.content_approver_user
        ).with_context(
            allowed_company_ids=[self.content_approver_user.company_id.id]
        ).search([])
        self.assertNotIn(other_brand, visible)
