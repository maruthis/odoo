from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterTwoWayBlacklistSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason_global_opt_out = cls.env.ref(
            "newsletter_compliance.suppression_reason_global_opt_out"
        )

    def test_native_blacklist_creates_suppression_entry(self):
        partner = self.env["res.partner"].create(
            {"name": "Native Blacklist", "email": "native.blacklist@example.com"}
        )

        self.env["mail.blacklist"].create({"email": "native.blacklist@example.com"})

        suppression = self.env["newsletter.suppression.entry"].search(
            [("partner_id", "=", partner.id), ("scope", "=", "global")]
        )
        self.assertTrue(suppression)
        self.assertEqual(suppression.reason_id.code, "GLOBAL_OPT_OUT")
        self.assertEqual(suppression.source, "odoo_blacklist")

    def test_no_partner_match_does_not_error(self):
        # No res.partner exists for this email - the sync should simply
        # skip creating a suppression entry (which requires a partner_id)
        # rather than raise.
        record = self.env["mail.blacklist"].create({"email": "no.partner.match@example.com"})
        self.assertTrue(record)

    def test_sync_loop_prevented(self):
        partner = self.env["res.partner"].create(
            {"name": "Loop Test", "email": "loop.test@example.com"}
        )
        purpose = self.env["newsletter.consent.purpose"].create(
            {
                "name": "Loop Purpose",
                "code": "LOOP_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )

        before_count = self.env["newsletter.suppression.entry"].search_count(
            [("partner_id", "=", partner.id)]
        )

        # Creating a suppression entry directly should sync to blacklist
        # without looping back to create a second suppression entry.
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason_global_opt_out.id,
                "source": "manual",
            }
        )

        after_count = self.env["newsletter.suppression.entry"].search_count(
            [("partner_id", "=", partner.id)]
        )
        self.assertEqual(after_count, before_count + 1)

        blacklisted = self.env["mail.blacklist"].search(
            [("email", "=", "loop.test@example.com")]
        )
        self.assertTrue(blacklisted)
