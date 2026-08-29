import datetime

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import config_service


@tagged("post_install", "-at_install")
class TestNewsletterConfigGuards(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.purpose = cls.env["newsletter.consent.purpose"].create(
            {
                "name": "Config Guard Purpose",
                "code": "CONFIG_GUARD_PURPOSE",
                "privacy_notice_version": "v1",
            }
        )
        cls.brand = cls.env["newsletter.campaign.brand"].create(
            {
                "name": "Config Guard Brand",
                "code": "CONFIG_GUARD_BRAND",
                "email_from": "configguard@example.com",
                "physical_address": "1 Config St",
                "default_consent_purpose_id": cls.purpose.id,
            }
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.operator = cls.env["res.users"].create(
            {
                "name": "Config Guard Operator",
                "login": "config_guard_operator_test",
                "group_ids": [
                    (
                        6, 0,
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
                "name": "Config Guard Approver",
                "login": "config_guard_approver_test",
                "group_ids": [
                    (
                        6, 0,
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
                "name": "Config Guard Reviewer",
                "login": "config_guard_reviewer_test",
                "group_ids": [
                    (
                        6, 0,
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

    def _run_preflight(self, email):
        partner = self.env["res.partner"].create({"name": email, "email": email})
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
        campaign = self.env["mailing.mailing"].create(
            {
                "name": "Config Guard Campaign %s" % email,
                "subject": "Config Guard Subject",
                "mailing_type": "mail",
                "mailing_model_id": self.partner_model.id,
                "mailing_domain": repr([("id", "in", partner.ids)]),
                "brand_id": self.brand.id,
                "consent_purpose_id": self.purpose.id,
                "email_from": "configguard@example.com",
                "body_html": "<p>Content</p>",
            }
        )
        campaign.action_submit_content_review()
        campaign.with_user(self.approver).action_approve_content()
        campaign.with_user(self.reviewer).action_approve_compliance()
        campaign.with_user(self.reviewer).action_run_compliance_preflight()
        return campaign, campaign.current_campaign_run_id

    def test_minimum_eligible_recipient_count_config_blocks_preflight(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.minimum_eligible_recipient_count", "5"
        )
        _campaign, run = self._run_preflight("config.min.recipients@example.com")
        self.assertEqual(run.state, "failed")
        self.assertIn("zero people", run.failure_reason or "")

    def test_dispatch_batch_size_defaults_from_config(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.dispatch_batch_size", "42"
        )
        _campaign, run = self._run_preflight("config.batch.size@example.com")
        self.assertEqual(run.execution_batch_size, 42)

    def test_maximum_retry_count_defaults_from_config(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.maximum_retry_count", "9"
        )
        _campaign, run = self._run_preflight("config.retry.count@example.com")
        self.assertEqual(run.maximum_retry_count, 9)

    def test_stale_preflight_blocks_execution_start(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.max_preflight_age_minutes", "30"
        )
        _campaign, run = self._run_preflight("config.stale.preflight@example.com")
        self.assertEqual(run.state, "passed")

        run.write(
            {"preflight_completed_at": run.preflight_completed_at - datetime.timedelta(hours=2)}
        )
        with self.assertRaises(UserError):
            run.with_user(self.operator).action_start_execution()

    def test_fresh_preflight_allows_execution_start(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.max_preflight_age_minutes", "30"
        )
        _campaign, run = self._run_preflight("config.fresh.preflight@example.com")
        run.with_user(self.operator).action_start_execution()
        self.assertEqual(run.state, "queued")

    def test_max_preflight_age_zero_disables_staleness_check(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.max_preflight_age_minutes", "0"
        )
        _campaign, run = self._run_preflight("config.disabled.staleness@example.com")
        run.write(
            {"preflight_completed_at": run.preflight_completed_at - datetime.timedelta(days=30)}
        )
        run.with_user(self.operator).action_start_execution()
        self.assertEqual(run.state, "queued")

    def test_audit_export_expiry_days_from_config(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.audit_export_expiry_days", "3"
        )
        export = self.env["newsletter.audit.export"].create({"export_type": "campaign"})
        expected_expiry = export.generated_at + datetime.timedelta(days=3)
        self.assertAlmostEqual(
            export.expires_at, expected_expiry, delta=datetime.timedelta(seconds=5)
        )

    def test_retention_policy_defaults_from_config(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.retention_batch_size", "250"
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "newsletter_compliance.retention_dry_run_default", "False"
        )
        policy = self.env["newsletter.retention.policy"].create(
            {
                "name": "Config Default Policy",
                "code": "CONFIG_DEFAULT_POLICY",
                "data_category": "suppression_history",
                "retention_period_days": 30,
                "expiry_action": "review",
            }
        )
        self.assertEqual(policy.batch_size, 250)
        self.assertFalse(policy.dry_run)


@tagged("post_install", "-at_install")
class TestNewsletterOperationsAdministratorRole(TransactionCase):
    def test_group_exists_and_implies_campaign_operator(self):
        group = self.env.ref("newsletter_compliance.group_newsletter_operations_admin")
        operator_group = self.env.ref("newsletter_compliance.group_newsletter_campaign_operator")
        self.assertIn(operator_group, group.implied_ids)

    def test_operations_admin_can_configure_settings(self):
        user = self.env["res.users"].create(
            {
                "name": "Operations Admin Test",
                "login": "operations_admin_test",
                "group_ids": [
                    (
                        6, 0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("mass_mailing.group_mass_mailing_user").id,
                            self.env.ref(
                                "newsletter_compliance.group_newsletter_operations_admin"
                            ).id,
                        ],
                    )
                ],
            }
        )
        self.assertTrue(
            user.has_group("newsletter_compliance.group_newsletter_campaign_operator")
        )
        self.assertFalse(
            user.has_group("newsletter_compliance.group_newsletter_compliance_admin")
        )
        self.assertFalse(
            user.has_group("newsletter_compliance.group_newsletter_content_approver")
        )
