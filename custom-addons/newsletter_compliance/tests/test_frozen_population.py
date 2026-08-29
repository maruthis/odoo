from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterFrozenPopulation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Frozen Population Purpose",
                "code": "FROZEN_POPULATION_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Frozen Population Brand",
                "code": "FROZEN_POPULATION_BRAND",
                "email_from": "frozen@example.com",
                "physical_address": "1 Frozen St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.reason_global_opt_out = cls.env.ref(
            "newsletter_compliance.suppression_reason_global_opt_out"
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Operator Frozen Test",
                "login": "operator_frozen_test",
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
                "name": "Approver Frozen Test",
                "login": "approver_frozen_test",
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
                "name": "Reviewer Frozen Test",
                "login": "reviewer_frozen_test",
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

    def _create_and_pass_preflight(self, domain):
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Frozen Population Campaign",
                "subject": "Frozen Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr(domain),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "frozen@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.operator).action_run_compliance_preflight()
        self.assertEqual(campaign.compliance_state, "ready")
        return campaign

    def test_contact_added_after_preflight_not_included(self):
        original = self._make_partner_with_consent(
            "Original Recipient", "original@frozen-test.example.com"
        )
        domain = [("email", "like", "@frozen-test.example.com")]
        campaign = self._create_and_pass_preflight(domain)

        run = campaign.current_campaign_run_id
        self.assertEqual(run.targeted_count, 1)

        # a new matching contact appears after the freeze
        self._make_partner_with_consent(
            "Late Arrival", "late@frozen-test.example.com"
        )

        res_ids = self.env[campaign.mailing_model_real].search(
            campaign._get_recipients_domain()
        ).ids
        self.assertIn(original.id, res_ids)
        self.assertEqual(len(res_ids), 1)

    def test_consent_withdrawn_after_preflight_blocks_at_dispatch(self):
        partner = self._make_partner_with_consent(
            "Withdraws Later", "withdraws.later@example.com"
        )
        domain = [("id", "in", partner.ids)]
        campaign = self._create_and_pass_preflight(domain)

        run = campaign.current_campaign_run_id
        decision = run.eligibility_ids.filtered(lambda e: e.recipient_res_id == partner.id)
        self.assertEqual(decision.status, "eligible")

        consent = self.env["newsletter.consent.record"].search(
            [("partner_id", "=", partner.id)]
        )
        consent.write({"status": "withdrawn", "withdrawn_at": "2026-03-01 10:00:00"})

        res_ids = self.env[campaign.mailing_model_real].search(
            campaign._get_recipients_domain()
        ).ids
        self.assertNotIn(partner.id, res_ids)
        self.assertEqual(decision.dispatch_state, "blocked")

    def test_global_suppression_added_after_preflight_blocks_at_dispatch(self):
        partner = self._make_partner_with_consent(
            "Suppressed Later", "suppressed.later@example.com"
        )
        domain = [("id", "in", partner.ids)]
        campaign = self._create_and_pass_preflight(domain)

        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason_global_opt_out.id,
                "source": "manual",
            }
        )

        res_ids = self.env[campaign.mailing_model_real].search(
            campaign._get_recipients_domain()
        ).ids
        self.assertNotIn(partner.id, res_ids)

    def test_already_sent_recipient_not_resent(self):
        partner = self._make_partner_with_consent(
            "Already Sent", "already.sent@example.com"
        )
        domain = [("id", "in", partner.ids)]
        campaign = self._create_and_pass_preflight(domain)

        run = campaign.current_campaign_run_id
        decision = run.eligibility_ids.filtered(lambda e: e.recipient_res_id == partner.id)
        decision.write({"dispatch_state": "sent"})

        res_ids = self.env[campaign.mailing_model_real].search(
            campaign._get_recipients_domain()
        ).ids
        self.assertNotIn(partner.id, res_ids)
