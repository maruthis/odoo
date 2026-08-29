from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterCampaignApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Product Updates R2",
                "code": "PRODUCT_UPDATES_R2",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Product",
                "code": "PRODUCT_BRAND",
                "email_from": "product@example.com",
                "physical_address": "1 Product Way, Springfield",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )

        cls.base_group_user = cls.env.ref("base.group_user")
        cls.mass_mailing_group = cls.env.ref("mass_mailing.group_mass_mailing_user")
        cls.group_content_approver = cls.env.ref(
            "newsletter_compliance.group_newsletter_content_approver"
        )
        cls.group_compliance_reviewer = cls.env.ref(
            "newsletter_compliance.group_newsletter_compliance_reviewer"
        )
        cls.group_user = cls.env.ref(
            "newsletter_compliance.group_newsletter_compliance_user"
        )

        cls.content_approver_user = cls.env["res.users"].create(
            {
                "name": "Content Approver Approval Test",
                "login": "content_approver_approval_test",
                "group_ids": [
                    (6, 0, [cls.base_group_user.id, cls.mass_mailing_group.id, cls.group_content_approver.id])
                ],
            }
        )
        cls.compliance_reviewer_user = cls.env["res.users"].create(
            {
                "name": "Compliance Reviewer Approval Test",
                "login": "compliance_reviewer_approval_test",
                "group_ids": [
                    (6, 0, [cls.base_group_user.id, cls.mass_mailing_group.id, cls.group_compliance_reviewer.id])
                ],
            }
        )
        cls.plain_user = cls.env["res.users"].create(
            {
                "name": "Plain Newsletter User",
                "login": "plain_newsletter_user_test",
                "group_ids": [(6, 0, [cls.base_group_user.id, cls.group_user.id])],
            }
        )

        cls.campaign = cls.env["mailing.mailing"].create(
            {
                "name": "Product Launch Newsletter",
                "subject": "New Product Launch",
                "mailing_type": "mail",
                "brand_id": cls.brand.id,
                "consent_purpose_id": cls.purpose.id,
                "email_from": "product@example.com",
                "body_html": "<p>Launch content</p>",
                "mailing_domain": "[]",
            }
        )
        cls.campaign.action_submit_content_review()

    def test_content_approval_creates_history_record(self):
        self.campaign.with_user(self.content_approver_user).action_approve_content()
        history = self.env["newsletter.campaign.approval"].search(
            [("mailing_id", "=", self.campaign.id), ("approval_type", "=", "content")]
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history.decision, "approved")
        self.assertEqual(history.reviewer_id, self.content_approver_user)
        self.assertEqual(history.approval_version, 1)

    def test_compliance_approval_creates_history_record(self):
        self.campaign.with_user(self.content_approver_user).action_approve_content()
        self.campaign.with_user(
            self.compliance_reviewer_user
        ).action_approve_compliance()
        history = self.env["newsletter.campaign.approval"].search(
            [
                ("mailing_id", "=", self.campaign.id),
                ("approval_type", "=", "compliance"),
            ]
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history.decision, "approved")
        self.assertEqual(history.reviewer_id, self.compliance_reviewer_user)

    def test_history_preserved_across_versions(self):
        self.campaign.with_user(self.content_approver_user).action_approve_content()
        self.campaign.with_user(
            self.compliance_reviewer_user
        ).action_approve_compliance()

        # A governed change invalidates the approval and creates a new
        # version; the earlier approval records must remain.
        self.campaign.write({"subject": "Updated Subject"})

        history = self.env["newsletter.campaign.approval"].search(
            [("mailing_id", "=", self.campaign.id)]
        )
        self.assertEqual(len(history), 3)  # content approved, compliance approved, invalidated
        decisions = history.mapped("decision")
        self.assertIn("approved", decisions)
        self.assertIn("invalidated", decisions)

    def test_ordinary_user_cannot_create_approval_record_directly(self):
        with self.assertRaises(AccessError):
            self.env["newsletter.campaign.approval"].with_user(
                self.plain_user
            ).create(
                {
                    "mailing_id": self.campaign.id,
                    "approval_version": 1,
                    "approval_type": "content",
                    "decision": "approved",
                    "reviewer_id": self.plain_user.id,
                }
            )

    def test_ordinary_user_cannot_delete_approval_record(self):
        self.campaign.with_user(self.content_approver_user).action_approve_content()
        history = self.env["newsletter.campaign.approval"].search(
            [("mailing_id", "=", self.campaign.id)], limit=1
        )
        with self.assertRaises(AccessError):
            history.with_user(self.plain_user).unlink()
