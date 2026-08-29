from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterSuppression(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Jane Doe", "email": "jane@example.com"}
        )
        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Product Updates",
                "code": "PRODUCT_UPDATES",
                "privacy_notice_version": "v1",
            }
        )
        cls.reason_unsubscribe = cls.env.ref(
            "newsletter_compliance.suppression_reason_unsubscribe"
        )
        cls.reason_hard_bounce = cls.env.ref(
            "newsletter_compliance.suppression_reason_hard_bounce"
        )

    def test_purpose_suppression_requires_purpose(self):
        with self.assertRaises(ValidationError):
            self.env["newsletter.suppression.entry"].create(
                {
                    "partner_id": self.partner.id,
                    "scope": "purpose",
                    "reason_id": self.reason_unsubscribe.id,
                    "source": "unsubscribe",
                }
            )

    def test_purpose_suppression_stays_scoped(self):
        suppression = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": self.partner.id,
                "scope": "purpose",
                "purpose_id": self.purpose.id,
                "reason_id": self.reason_unsubscribe.id,
                "source": "unsubscribe",
            }
        )
        self.assertEqual(suppression.scope, "purpose")
        blacklisted = self.env["mail.blacklist"].search(
            [("email", "=", "jane@example.com")]
        )
        self.assertFalse(blacklisted)

    def test_global_suppression_syncs_blacklist(self):
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": self.partner.id,
                "scope": "global",
                "reason_id": self.reason_hard_bounce.id,
                "source": "bounce",
            }
        )
        blacklisted = self.env["mail.blacklist"].search(
            [("email", "=", "jane@example.com")]
        )
        self.assertTrue(blacklisted)

    def test_suppression_gets_unique_reference(self):
        suppression = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": self.partner.id,
                "scope": "global",
                "reason_id": self.reason_hard_bounce.id,
                "source": "bounce",
            }
        )
        self.assertTrue(suppression.reference.startswith("SUP-"))

    def test_suppression_cannot_be_deleted(self):
        suppression = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": self.partner.id,
                "scope": "global",
                "reason_id": self.reason_hard_bounce.id,
                "source": "bounce",
            }
        )
        with self.assertRaises(UserError):
            suppression.unlink()

    def test_ordinary_user_cannot_reinstate(self):
        suppression = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": self.partner.id,
                "scope": "global",
                "reason_id": self.reason_hard_bounce.id,
                "source": "bounce",
            }
        )
        user_group = self.env.ref(
            "newsletter_compliance.group_newsletter_compliance_user"
        )
        ordinary_user = self.env["res.users"].create(
            {
                "name": "Ordinary User",
                "login": "ordinary_user_test",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id, user_group.id])],
            }
        )
        # Ordinary users don't even have create rights on the wizard model;
        # the model-level ACL blocks them before the action's own group
        # check would run.
        with self.assertRaises(AccessError):
            self.env["newsletter.reinstate.suppression.wizard"].with_user(
                ordinary_user
            ).create(
                {
                    "suppression_id": suppression.id,
                    "reinstatement_reason": "Not authorized",
                }
            )

    def test_admin_can_reinstate_with_reason(self):
        suppression = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": self.partner.id,
                "scope": "global",
                "reason_id": self.reason_hard_bounce.id,
                "source": "bounce",
            }
        )
        admin_group = self.env.ref(
            "newsletter_compliance.group_newsletter_compliance_admin"
        )
        admin_user = self.env["res.users"].create(
            {
                "name": "Compliance Admin",
                "login": "compliance_admin_test",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id, admin_group.id])],
            }
        )
        wizard = (
            self.env["newsletter.reinstate.suppression.wizard"]
            .with_user(admin_user)
            .create(
                {
                    "suppression_id": suppression.id,
                    "reinstatement_reason": "Address corrected",
                }
            )
        )
        wizard.action_confirm()

        self.assertFalse(suppression.active)
        self.assertTrue(suppression.reinstated_at)
        self.assertEqual(suppression.reinstated_by_id, admin_user)

        # Historical entry remains (just inactive, never deleted)
        self.assertTrue(
            self.env["newsletter.suppression.entry"]
            .with_context(active_test=False)
            .search([("id", "=", suppression.id)])
        )
