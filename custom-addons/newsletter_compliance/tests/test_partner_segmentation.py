from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterPartnerSegmentation(TransactionCase):
    def test_segmentation_fields_are_writable_and_usable_in_domain(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Segmentation Test",
                "email": "segmentation.test@example.com",
                "newsletter_recipient_type": "business",
                "newsletter_segment": "Enterprise",
                "newsletter_region": "EMEA",
            }
        )
        self.assertEqual(partner.newsletter_recipient_type, "business")
        self.assertEqual(partner.newsletter_segment, "Enterprise")
        self.assertEqual(partner.newsletter_region, "EMEA")

        found = self.env["res.partner"].search(
            [("newsletter_recipient_type", "=", "business"), ("newsletter_segment", "=", "Enterprise")]
        )
        self.assertIn(partner, found)


@tagged("post_install", "-at_install")
class TestNewsletterEligibilitySummary(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.allowed_purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Eligibility Allowed Purpose",
                "code": "ELIGIBILITY_ALLOWED",
                "privacy_notice_version": "v1",
            }
        )
        cls.suppressed_purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Eligibility Suppressed Purpose",
                "code": "ELIGIBILITY_SUPPRESSED",
                "privacy_notice_version": "v1",
            }
        )
        cls.no_consent_purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Eligibility No Consent Purpose",
                "code": "ELIGIBILITY_NO_CONSENT",
                "privacy_notice_version": "v1",
            }
        )
        cls.reason = cls.env.ref("newsletter_compliance.suppression_reason_manual")

    def test_grid_reflects_allowed_suppressed_and_no_consent(self):
        partner = self.env["res.partner"].create(
            {"name": "Eligibility Grid Test", "email": "eligibility.grid@example.com"}
        )
        self.env["newsletter.consent.record"].create(
            {
                "partner_id": partner.id,
                "purpose_id": self.allowed_purpose.id,
                "status": "active",
                "given_at": "2026-01-01 10:00:00",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )
        self.env["newsletter.consent.record"].create(
            {
                "partner_id": partner.id,
                "purpose_id": self.suppressed_purpose.id,
                "status": "active",
                "given_at": "2026-01-01 10:00:00",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "purpose",
                "purpose_id": self.suppressed_purpose.id,
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )

        summary = partner.newsletter_eligibility_summary
        self.assertIn(self.allowed_purpose.name, summary)
        self.assertIn("Allowed", summary)
        self.assertIn(self.suppressed_purpose.name, summary)
        self.assertIn("Suppressed", summary)
        self.assertIn(self.no_consent_purpose.name, summary)
        self.assertIn("No Consent", summary)

    def test_global_suppression_marks_every_purpose_suppressed(self):
        partner = self.env["res.partner"].create(
            {"name": "Global Suppression Grid Test", "email": "global.grid@example.com"}
        )
        self.env["newsletter.consent.record"].create(
            {
                "partner_id": partner.id,
                "purpose_id": self.allowed_purpose.id,
                "status": "active",
                "given_at": "2026-01-01 10:00:00",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )

        summary = partner.newsletter_eligibility_summary
        # Even though there's an active consent record for allowed_purpose,
        # a global suppression must override it in the displayed grid.
        rows = summary.split("<tr>")
        allowed_purpose_row = next(r for r in rows if self.allowed_purpose.name in r)
        self.assertIn("Suppressed", allowed_purpose_row)
