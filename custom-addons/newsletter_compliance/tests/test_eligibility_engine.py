from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterEligibilityEngine(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Healthcare Newsletter R3",
                "code": "HEALTHCARE_R3",
                "privacy_notice_version": "v1",
            }
        )
        cls.other_purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Promotions R3",
                "code": "PROMOTIONS_R3",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Healthcare R3",
                "code": "HEALTHCARE_BRAND_R3",
                "email_from": "healthcare@example.com",
                "physical_address": "1 Health St, Springfield",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.reason_global_opt_out = cls.env.ref(
            "newsletter_compliance.suppression_reason_global_opt_out"
        )
        cls.reason_purpose_opt_out = cls.env.ref(
            "newsletter_compliance.suppression_reason_purpose_opt_out"
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.approver = cls.env["res.users"].create(
            {
                "name": "Approver Eligibility Test",
                "login": "approver_eligibility_test",
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
                "name": "Reviewer Eligibility Test",
                "login": "reviewer_eligibility_test",
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

    def _make_partner(self, name, email):
        return self.env["res.partner"].create({"name": name, "email": email})

    def _give_active_consent(self, partner, purpose=None):
        return self.env["newsletter.consent.record"].create(
            {
                "partner_id": partner.id,
                "purpose_id": (purpose or self.purpose).id,
                "status": "active",
                "given_at": "2026-01-01 10:00:00",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )

    def _create_campaign(self, partner_ids):
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Eligibility Test Campaign",
                "subject": "Test Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner_ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "healthcare@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        self.assertEqual(campaign.compliance_state, "preflight_required")
        return campaign

    def _run_preflight(self, campaign):
        campaign.with_user(self.reviewer).action_run_compliance_preflight()

    def _decision_for(self, campaign, email):
        return campaign.current_campaign_run_id.eligibility_ids.filtered(
            lambda e: e.email_normalized == email
        )

    def test_active_matching_consent_is_eligible(self):
        partner = self._make_partner("John Eligible", "john.eligible@example.com")
        self._give_active_consent(partner)
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "john.eligible@example.com")
        self.assertEqual(decision.status, "eligible")
        self.assertEqual(decision.reason_code, "eligible")
        self.assertEqual(campaign.compliance_state, "ready")

    def test_no_consent_excluded(self):
        partner = self._make_partner("No Consent", "no.consent@example.com")
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "no.consent@example.com")
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "missing_consent")

    def test_consent_for_different_purpose_excluded(self):
        partner = self._make_partner("Wrong Purpose", "wrong.purpose@example.com")
        self._give_active_consent(partner, purpose=self.other_purpose)
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "wrong.purpose@example.com")
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "missing_consent")

    def test_withdrawn_consent_excluded(self):
        partner = self._make_partner("Withdrawn", "withdrawn@example.com")
        consent = self._give_active_consent(partner)
        consent.write({"status": "withdrawn", "withdrawn_at": "2026-02-01 10:00:00"})
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "withdrawn@example.com")
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "withdrawn_consent")
        self.assertEqual(decision.consent_record_id, consent)

    def test_expired_consent_excluded(self):
        partner = self._make_partner("Expired", "expired@example.com")
        consent = self.env["newsletter.consent.record"].create(
            {
                "partner_id": partner.id,
                "purpose_id": self.purpose.id,
                "status": "active",
                "given_at": "2020-01-01 10:00:00",
                "expires_at": "2020-06-01 10:00:00",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )
        consent.with_context(skip_compliance_invalidation=True).write({"status": "expired"})
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "expired@example.com")
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "expired_consent")

    def test_pending_consent_excluded(self):
        partner = self._make_partner("Pending", "pending@example.com")
        self.env["newsletter.consent.record"].create(
            {
                "partner_id": partner.id,
                "purpose_id": self.purpose.id,
                "status": "pending",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": "v1",
            }
        )
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "pending@example.com")
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "pending_consent")

    def test_odoo_global_blacklist_excludes(self):
        partner = self._make_partner("Blacklisted", "blacklisted@example.com")
        self._give_active_consent(partner)
        self.env["mail.blacklist"].sudo()._add("blacklisted@example.com")
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "blacklisted@example.com")
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "global_blacklist")

    def test_custom_global_suppression_excludes(self):
        # Uses the MANUAL reason rather than GLOBAL_OPT_OUT: the latter
        # auto-syncs to Odoo's own mail.blacklist (R1 behavior), which
        # would make "global_blacklist" win by decision-order precedence
        # instead of exercising the custom suppression path in isolation.
        partner = self._make_partner("Globally Suppressed", "global.suppressed@example.com")
        self._give_active_consent(partner)
        reason_manual = self.env.ref("newsletter_compliance.suppression_reason_manual")
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": reason_manual.id,
                "source": "manual",
            }
        )
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "global.suppressed@example.com")
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "global_suppression")

    def test_purpose_suppression_matching_campaign_excludes(self):
        partner = self._make_partner("Purpose Suppressed", "purpose.suppressed@example.com")
        self._give_active_consent(partner)
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "purpose",
                "purpose_id": self.purpose.id,
                "reason_id": self.reason_purpose_opt_out.id,
                "source": "manual",
            }
        )
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "purpose.suppressed@example.com")
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "purpose_suppression")

    def test_purpose_suppression_for_other_purpose_does_not_exclude(self):
        partner = self._make_partner("Other Purpose Suppressed", "other.suppressed@example.com")
        self._give_active_consent(partner)
        self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "purpose",
                "purpose_id": self.other_purpose.id,
                "reason_id": self.reason_purpose_opt_out.id,
                "source": "manual",
            }
        )
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = self._decision_for(campaign, "other.suppressed@example.com")
        self.assertEqual(decision.status, "eligible")

    def test_missing_email_excluded(self):
        partner = self._make_partner("No Email", False)
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = campaign.current_campaign_run_id.eligibility_ids.filtered(
            lambda e: e.recipient_res_id == partner.id
        )
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "missing_email")

    def test_invalid_email_excluded(self):
        partner = self._make_partner("Bad Email", "not-an-email")
        campaign = self._create_campaign(partner.ids)
        self._run_preflight(campaign)

        decision = campaign.current_campaign_run_id.eligibility_ids.filtered(
            lambda e: e.recipient_res_id == partner.id
        )
        self.assertEqual(decision.status, "excluded")
        self.assertEqual(decision.reason_code, "invalid_email")

    def test_case_variation_duplicates_deduplicated(self):
        partner1 = self._make_partner("Dup One", "Dup@Example.com")
        partner2 = self._make_partner("Dup Two", "dup@example.com")
        self._give_active_consent(partner1)
        self._give_active_consent(partner2)
        campaign = self._create_campaign(partner1.ids + partner2.ids)
        self._run_preflight(campaign)

        run = campaign.current_campaign_run_id
        decisions = run.eligibility_ids.filtered(lambda e: e.email_normalized == "dup@example.com")
        self.assertEqual(len(decisions), 2)
        statuses = decisions.mapped("status")
        self.assertEqual(statuses.count("eligible"), 1)
        self.assertEqual(statuses.count("excluded"), 1)

        duplicate = decisions.filtered(lambda e: e.status == "excluded")
        self.assertEqual(duplicate.reason_code, "duplicate_email")
        self.assertTrue(duplicate.duplicate_of_id)

    def test_reconciliation_every_target_has_one_decision(self):
        partners = self.env["res.partner"].create(
            [
                {"name": "Recon A", "email": "recon.a@example.com"},
                {"name": "Recon B", "email": "recon.b@example.com"},
                {"name": "Recon C", "email": False},
            ]
        )
        self._give_active_consent(partners[0])
        campaign = self._create_campaign(partners.ids)
        self._run_preflight(campaign)

        run = campaign.current_campaign_run_id
        self.assertEqual(len(run.eligibility_ids), 3)
        self.assertEqual(run.targeted_count, 3)
        self.assertEqual(run.eligible_count + run.excluded_count, run.targeted_count)
        self.assertEqual(run.state, "passed")
