from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterPreflightWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Workflow Purpose",
                "code": "WORKFLOW_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Workflow Brand",
                "code": "WORKFLOW_BRAND",
                "email_from": "workflow@example.com",
                "physical_address": "1 Workflow St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Campaign Operator Workflow",
                "login": "campaign_operator_workflow_test",
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
                "name": "Content Approver Workflow",
                "login": "content_approver_workflow_test",
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
                "name": "Compliance Reviewer Workflow",
                "login": "compliance_reviewer_workflow_test",
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
                "name": "Workflow Campaign",
                "subject": "Workflow Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner_ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "workflow@example.com",
                "body_html": "<p>Content</p>",
            }
        )

    def _approve_through_preflight_required(self, campaign):
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        self.assertEqual(campaign.compliance_state, "preflight_required")

    def test_draft_campaign_cannot_preflight(self):
        partner = self._make_partner_with_consent("Draft Partner", "draft.partner@example.com")
        campaign = self._create_campaign(partner.ids)
        with self.assertRaises(UserError):
            campaign.with_user(self.operator).action_run_compliance_preflight()

    def test_content_review_campaign_cannot_preflight(self):
        partner = self._make_partner_with_consent("CR Partner", "cr.partner@example.com")
        campaign = self._create_campaign(partner.ids)
        campaign.action_submit_content_review()
        with self.assertRaises(UserError):
            campaign.with_user(self.operator).action_run_compliance_preflight()

    def test_compliance_approved_campaign_can_preflight(self):
        partner = self._make_partner_with_consent("Approved Partner", "approved.partner@example.com")
        campaign = self._create_campaign(partner.ids)
        self._approve_through_preflight_required(campaign)
        campaign.with_user(self.operator).action_run_compliance_preflight()
        self.assertEqual(campaign.compliance_state, "ready")

    def test_successful_run_moves_to_ready(self):
        partner = self._make_partner_with_consent("Ready Partner", "ready.partner@example.com")
        campaign = self._create_campaign(partner.ids)
        self._approve_through_preflight_required(campaign)
        campaign.with_user(self.operator).action_run_compliance_preflight()

        self.assertEqual(campaign.compliance_state, "ready")
        self.assertEqual(campaign.preflight_status, "passed")
        self.assertTrue(campaign.current_campaign_run_id.frozen)

    def test_failed_run_stays_blocked(self):
        # No recipients at all -> zero eligible -> preflight should fail
        campaign = self._create_campaign([])
        self._approve_through_preflight_required(campaign)
        campaign.with_user(self.operator).action_run_compliance_preflight()

        self.assertNotEqual(campaign.compliance_state, "ready")
        self.assertEqual(campaign.compliance_state, "preflight_required")
        self.assertEqual(campaign.current_campaign_run_id.state, "failed")

    def test_campaign_change_invalidates_run(self):
        partner = self._make_partner_with_consent("Invalidate Partner", "invalidate.partner@example.com")
        campaign = self._create_campaign(partner.ids)
        self._approve_through_preflight_required(campaign)
        campaign.with_user(self.operator).action_run_compliance_preflight()
        first_run = campaign.current_campaign_run_id
        self.assertEqual(campaign.compliance_state, "ready")

        campaign.write({"subject": "Changed Subject"})

        self.assertEqual(campaign.compliance_state, "draft")
        self.assertFalse(campaign.current_campaign_run_id)
        self.assertEqual(first_run.state, "invalidated")

    def test_rerun_creates_new_run_old_run_retained(self):
        partner = self._make_partner_with_consent("Rerun Partner", "rerun.partner@example.com")
        campaign = self._create_campaign(partner.ids)
        self._approve_through_preflight_required(campaign)
        campaign.with_user(self.operator).action_run_compliance_preflight()
        first_run = campaign.current_campaign_run_id

        campaign.write({"subject": "Rerun Subject Change"})
        self.assertEqual(campaign.compliance_state, "draft")
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.operator).action_run_compliance_preflight()
        second_run = campaign.current_campaign_run_id

        self.assertNotEqual(first_run.id, second_run.id)
        self.assertEqual(len(campaign.campaign_run_ids), 2)
        self.assertTrue(first_run.exists())

    def test_mailing_list_opt_out_excludes(self):
        mailing_list = self.env["mailing.list"].create({"name": "Workflow List"})
        contact = self.env["mailing.contact"].create(
            {
                "name": "List Contact",
                "email": "list.contact@example.com",
                "subscription_ids": [(0, 0, {"list_id": mailing_list.id, "opt_out": True})],
            }
        )
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "List Campaign",
                "subject": "List Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.env.ref("mass_mailing.model_mailing_list").id,
                "contact_list_ids": [(6, 0, [mailing_list.id])],
                "mailing_domain": repr([("list_ids", "in", [mailing_list.id])]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "workflow@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        self._approve_through_preflight_required(campaign)
        campaign.with_user(self.operator).action_run_compliance_preflight()

        run = campaign.current_campaign_run_id
        decision = run.eligibility_ids.filtered(
            lambda e: e.recipient_res_id == contact.id
        )
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "mailing_list_opt_out")
