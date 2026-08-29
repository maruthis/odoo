from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterComplianceSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref(
            "newsletter_compliance.group_newsletter_compliance_user"
        )
        cls.group_reviewer = cls.env.ref(
            "newsletter_compliance.group_newsletter_compliance_reviewer"
        )
        cls.group_admin = cls.env.ref(
            "newsletter_compliance.group_newsletter_compliance_admin"
        )
        cls.group_auditor = cls.env.ref(
            "newsletter_compliance.group_newsletter_compliance_auditor"
        )

        cls.newsletter_user = cls.env["res.users"].create(
            {
                "name": "Newsletter User",
                "login": "newsletter_user_test",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.group_user.id])],
            }
        )
        cls.reviewer_user = cls.env["res.users"].create(
            {
                "name": "Compliance Reviewer",
                "login": "compliance_reviewer_test",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.group_reviewer.id])],
            }
        )
        cls.admin_user = cls.env["res.users"].create(
            {
                "name": "Compliance Admin",
                "login": "compliance_admin_sec_test",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.group_admin.id])],
            }
        )
        cls.auditor_user = cls.env["res.users"].create(
            {
                "name": "Audit Reviewer",
                "login": "audit_reviewer_test",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id, cls.group_auditor.id])],
            }
        )

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Corporate Newsletter",
                "code": "CORPORATE",
                "privacy_notice_version": "v1",
            }
        )

    def test_ordinary_user_cannot_configure_purposes(self):
        with self.assertRaises(AccessError):
            self.env["newsletter.consent.purpose"].with_user(
                self.newsletter_user
            ).create(
                {
                    "name": "Unauthorized Purpose",
                    "code": "UNAUTH",
                    "privacy_notice_version": "v1",
                }
            )

    def test_reviewer_can_review_consent_records(self):
        partner = self.env["res.partner"].create(
            {"name": "Reviewer Target", "email": "reviewer.target@example.com"}
        )
        consent = self.env["newsletter.consent.record"].with_user(
            self.reviewer_user
        ).create(
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
        self.assertTrue(consent)

    def test_admin_can_configure_master_data(self):
        purpose = self.env["newsletter.consent.purpose"].with_user(
            self.admin_user
        ).create(
            {
                "name": "Admin Created Purpose",
                "code": "ADMIN_CREATED",
                "privacy_notice_version": "v1",
            }
        )
        self.assertTrue(purpose)

    def test_auditor_has_read_only_access(self):
        purposes = self.env["newsletter.consent.purpose"].with_user(
            self.auditor_user
        ).search([])
        self.assertIn(self.purpose, purposes)

        with self.assertRaises(AccessError):
            self.env["newsletter.consent.purpose"].with_user(
                self.auditor_user
            ).create(
                {
                    "name": "Auditor Purpose",
                    "code": "AUDITOR",
                    "privacy_notice_version": "v1",
                }
            )

    def test_company_isolated_records(self):
        other_company = self.env["res.company"].create({"name": "Other Co"})
        other_purpose = self.env["newsletter.consent.purpose"].create(
            {
                "name": "Other Company Purpose",
                "code": "OTHERCO",
                "privacy_notice_version": "v1",
                "company_id": other_company.id,
            }
        )

        visible = self.env["newsletter.consent.purpose"].with_user(
            self.admin_user
        ).with_context(
            allowed_company_ids=[self.admin_user.company_id.id]
        ).search([])
        self.assertNotIn(other_purpose, visible)
