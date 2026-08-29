from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import retention_service


@tagged("post_install", "-at_install")
class TestNewsletterLegalHold(TransactionCase):
    def test_create_posts_chatter_message(self):
        hold = self.env["newsletter.legal.hold"].create(
            {
                "name": "Litigation Hold A",
                "reason": "Pending litigation - preserve all data.",
                "scope_type": "company",
            }
        )
        self.assertTrue(hold.reference)
        self.assertTrue(hold.message_ids)

    def test_release_requires_reason(self):
        hold = self.env["newsletter.legal.hold"].create(
            {
                "name": "Release Reason Test",
                "reason": "Investigation",
                "scope_type": "company",
            }
        )
        with self.assertRaises(UserError):
            hold.action_release(reason=False)

    def test_release_requires_active_status(self):
        hold = self.env["newsletter.legal.hold"].create(
            {
                "name": "Already Released",
                "reason": "Investigation",
                "scope_type": "company",
            }
        )
        hold.action_release(reason="Case closed")
        with self.assertRaises(UserError):
            hold.action_release(reason="Try again")

    def test_recipient_scope_hold_matches_only_scoped_partner(self):
        partner_held = self.env["res.partner"].create({"name": "Held Partner"})
        partner_free = self.env["res.partner"].create({"name": "Free Partner"})
        hold = self.env["newsletter.legal.hold"].create(
            {
                "name": "Recipient Scope Hold",
                "reason": "Specific recipient investigation",
                "scope_type": "recipient",
                "scope_partner_ids": [(6, 0, [partner_held.id])],
            }
        )
        self.assertTrue(hold.is_partner_held(partner_held.id))
        self.assertFalse(hold.is_partner_held(partner_free.id))

    def test_company_scope_hold_matches_any_partner(self):
        partner = self.env["res.partner"].create({"name": "Any Partner"})
        hold = self.env["newsletter.legal.hold"].create(
            {
                "name": "Company Wide Hold",
                "reason": "Regulator investigation - freeze everything",
                "scope_type": "company",
            }
        )
        self.assertTrue(hold.is_partner_held(partner.id))

    def test_released_hold_no_longer_matches(self):
        partner = self.env["res.partner"].create({"name": "Released Scope Partner"})
        hold = self.env["newsletter.legal.hold"].create(
            {
                "name": "Temporary Hold",
                "reason": "Short investigation",
                "scope_type": "recipient",
                "scope_partner_ids": [(6, 0, [partner.id])],
            }
        )
        self.assertTrue(hold.is_partner_held(partner.id))
        hold.action_release(reason="Investigation closed")
        self.assertFalse(hold.is_partner_held(partner.id))

    def test_retention_service_respects_legal_hold(self):
        partner = self.env["res.partner"].create({"name": "Retention Hold Partner"})
        reason = self.env.ref("newsletter_compliance.suppression_reason_manual")
        entry = self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": reason.id,
                "source": "manual",
            }
        )
        self.env["newsletter.legal.hold"].create(
            {
                "name": "Blocks Retention",
                "reason": "Legal preservation",
                "scope_type": "recipient",
                "scope_partner_ids": [(6, 0, [partner.id])],
            }
        )
        self.assertTrue(retention_service.is_legal_held(self.env, entry))
