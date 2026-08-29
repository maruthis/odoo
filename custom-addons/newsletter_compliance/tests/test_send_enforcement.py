from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterSendEnforcement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Send Enforcement Purpose",
                "code": "SEND_ENFORCEMENT_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Send Enforcement Brand",
                "code": "SEND_ENFORCEMENT_BRAND",
                "email_from": "send@example.com",
                "physical_address": "1 Send St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Send Test",
                "login": "operator_send_test",
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
                "name": "Approver Send Test",
                "login": "approver_send_test",
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
                "name": "Reviewer Send Test",
                "login": "reviewer_send_test",
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

    def _create_campaign(self, partner_ids):
        return self.env["mailing.mailing"].create(
            {
                "name": "Send Enforcement Campaign",
                "subject": "Send Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner_ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "send@example.com",
                "body_html": "<p>Content</p>",
            }
        )

    def test_send_blocked_without_preflight(self):
        partner = self._make_partner_with_consent("No Preflight", "no.preflight@example.com")
        campaign = self._create_campaign(partner.ids)
        with self.assertRaises(UserError):
            campaign.action_put_in_queue()

    def test_send_blocked_after_failed_preflight(self):
        campaign = self._create_campaign([])
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.operator).action_run_compliance_preflight()
        self.assertEqual(campaign.current_campaign_run_id.state, "failed")

        with self.assertRaises(UserError):
            campaign.action_put_in_queue()

    def test_send_blocked_when_run_not_frozen(self):
        partner = self._make_partner_with_consent("Unfrozen", "unfrozen@example.com")
        campaign = self._create_campaign(partner.ids)
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.operator).action_run_compliance_preflight()
        self.assertEqual(campaign.compliance_state, "ready")

        # simulate an unfrozen run reaching "ready" (should not normally
        # happen through the UI, but the send-blocking check must not rely
        # solely on compliance_state)
        campaign.current_campaign_run_id.write({"frozen": False})

        with self.assertRaises(UserError):
            campaign.action_put_in_queue()

    def test_send_allowed_with_passed_frozen_run(self):
        partner = self._make_partner_with_consent("Frozen Ready", "frozen.ready@example.com")
        campaign = self._create_campaign(partner.ids)
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.operator).action_run_compliance_preflight()

        self.assertEqual(campaign.compliance_state, "ready")
        self.assertTrue(campaign.current_campaign_run_id.frozen)
        # should not raise
        campaign.with_user(self.operator).action_put_in_queue()
        self.assertEqual(campaign.state, "in_queue")

    def test_direct_rpc_call_blocked_when_not_compliant(self):
        partner = self._make_partner_with_consent("Direct RPC", "direct.rpc@example.com")
        campaign = self._create_campaign(partner.ids)
        # calling the lower-level send method directly, bypassing any UI
        with self.assertRaises(UserError):
            campaign.action_send_mail()
