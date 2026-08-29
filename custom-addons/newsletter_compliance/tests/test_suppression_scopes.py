import datetime

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import suppression_service

EVAL_TIME = fields.Datetime.now() + datetime.timedelta(days=1)


@tagged("post_install", "-at_install")
class TestNewsletterSuppressionScopes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason = cls.env.ref("newsletter_compliance.suppression_reason_manual")
        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Scope Test Purpose",
                "code": "SCOPE_TEST_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Scope Test Brand",
                "code": "SCOPE_TEST_BRAND",
                "email_from": "scopetest@example.com",
                "physical_address": "1 Scope St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.other_brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Other Brand",
                "code": "OTHER_BRAND",
                "email_from": "other@example.com",
                "physical_address": "2 Other St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

    def _make_mailing(self, brand, name="Scope Test Mailing"):
        partner = self.env["res.partner"].create({"name": name, "email": f"{name}@example.com"})
        return partner, self.env["mailing.mailing"].create(
            {
                "name": name,
                "subject": "Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": brand.email_from,
                "body_html": "<p>Content</p>",
            }
        )

    def test_brand_scope_requires_brand_id(self):
        partner = self.env["res.partner"].create({"name": "Brand Scope Test", "email": "b@example.com"})
        with self.assertRaises(ValidationError):
            self.env["newsletter.suppression.entry"].create(
                {
                    "partner_id": partner.id,
                    "scope": "brand",
                    "reason_id": self.reason.id,
                    "source": "manual",
                }
            )

    def test_campaign_scope_requires_campaign_mailing_id(self):
        partner = self.env["res.partner"].create({"name": "Campaign Scope Test", "email": "c@example.com"})
        with self.assertRaises(ValidationError):
            self.env["newsletter.suppression.entry"].create(
                {
                    "partner_id": partner.id,
                    "scope": "campaign",
                    "reason_id": self.reason.id,
                    "source": "manual",
                }
            )

    def test_brand_suppression_blocks_only_that_brand(self):
        partner, mailing_a = self._make_mailing(self.brand, "brand-block-a")
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "brand",
                "brand_id": self.brand.id,
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )

        blocked = suppression_service.get_applicable_suppressions_by_email(
            self.env, [partner.email], self.purpose.id, [], EVAL_TIME,
            brand_id=self.brand.id, campaign_mailing_id=mailing_a.id,
        )
        self.assertIn(partner.email, blocked)

        not_blocked = suppression_service.get_applicable_suppressions_by_email(
            self.env, [partner.email], self.purpose.id, [], EVAL_TIME,
            brand_id=self.other_brand.id, campaign_mailing_id=False,
        )
        self.assertNotIn(partner.email, not_blocked)

    def test_campaign_suppression_blocks_only_that_one_mailing(self):
        partner, mailing_a = self._make_mailing(self.brand, "campaign-block-a")
        _partner_b, mailing_b = self._make_mailing(self.brand, "campaign-block-b")

        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "campaign",
                "campaign_mailing_id": mailing_a.id,
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )

        blocked = suppression_service.get_applicable_suppressions_by_email(
            self.env, [partner.email], self.purpose.id, [], EVAL_TIME,
            campaign_mailing_id=mailing_a.id,
        )
        self.assertIn(partner.email, blocked)

        not_blocked = suppression_service.get_applicable_suppressions_by_email(
            self.env, [partner.email], self.purpose.id, [], EVAL_TIME,
            campaign_mailing_id=mailing_b.id,
        )
        self.assertNotIn(partner.email, not_blocked)

    def test_global_suppression_still_wins_over_brand(self):
        partner, mailing_a = self._make_mailing(self.brand, "global-wins-a")
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )
        blocked = suppression_service.get_applicable_suppressions_by_email(
            self.env, [partner.email], self.purpose.id, [], EVAL_TIME,
            brand_id=self.brand.id, campaign_mailing_id=mailing_a.id,
        )
        self.assertIn(partner.email, blocked)
        self.assertEqual(blocked[partner.email].scope, "global")

    def test_brand_scoped_suppression_never_syncs_to_native_blacklist(self):
        partner = self.env["res.partner"].create(
            {"name": "Brand No Sync", "email": "brand.no.sync@example.com"}
        )
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "brand",
                "brand_id": self.brand.id,
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )
        blacklisted = self.env["mail.blacklist"].search([("email", "=", "brand.no.sync@example.com")])
        self.assertFalse(blacklisted)

    def test_preflight_excludes_recipient_with_campaign_scoped_suppression(self):
        partner, mailing = self._make_mailing(self.brand, "preflight-campaign-scope")
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
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "campaign",
                "campaign_mailing_id": mailing.id,
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )

        operator = self.env["res.users"].create(
            {
                "name": "Preflight Scope Operator",
                "login": "preflight_scope_operator_test",
                "group_ids": [
                    (
                        6, 0,
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
        mailing.action_submit_content_review()
        approver = self.env["res.users"].create(
            {
                "name": "Preflight Scope Approver",
                "login": "preflight_scope_approver_test",
                "group_ids": [
                    (
                        6, 0,
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
        mailing.with_user(approver).action_approve_content()
        mailing.with_user(operator).action_approve_compliance()
        mailing.with_user(operator).action_run_compliance_preflight()

        run = mailing.current_campaign_run_id
        eligibility = run.eligibility_ids.filtered(lambda e: e.partner_id == partner)
        self.assertEqual(eligibility.status, "excluded")
        self.assertEqual(eligibility.reason_code, "campaign_suppression")
