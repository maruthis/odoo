import datetime

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.newsletter_compliance.services import retention_service


@tagged("post_install", "-at_install")
class TestNewsletterRetention(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason = cls.env.ref("newsletter_compliance.suppression_reason_manual")
        cls.policy = cls.env["newsletter.retention.policy"].create(
            {
                "name": "Test Suppression Retention",
                "code": "TEST_SUPPRESSION_RETENTION",
                "data_category": "suppression_history",
                "retention_period_days": 30,
                "retention_trigger": "record_created",
                "expiry_action": "pseudonymize",
                "dry_run": False,
                "batch_size": 100,
            }
        )

    def _make_entry(self, email):
        partner = self.env["res.partner"].create({"name": email, "email": email})
        return self.env["newsletter.suppression.entry"].create(
            {
                "partner_id": partner.id,
                "scope": "global",
                "reason_id": self.reason.id,
                "source": "manual",
            }
        )

    def test_compute_retain_until_uses_trigger_field(self):
        entry = self._make_entry("retain.until@example.com")
        retain_until = retention_service.compute_retain_until(self.env, self.policy, entry)
        expected = entry.effective_from + datetime.timedelta(days=30)
        self.assertEqual(retain_until, expected)

    def test_assign_retention_stamps_record(self):
        entry = self._make_entry("assign.retention@example.com")
        retention_service.assign_retention(self.env, self.policy, entry)
        self.assertEqual(entry.retention_policy_id, self.policy)
        self.assertTrue(entry.retain_until)

    def test_evaluate_record_retain_when_not_expired(self):
        entry = self._make_entry("not.expired@example.com")
        retention_service.assign_retention(self.env, self.policy, entry)
        self.assertEqual(retention_service.evaluate_record(self.env, entry, self.policy), "retain")

    def test_evaluate_record_expiry_action_when_past_due(self):
        entry = self._make_entry("past.due@example.com")
        entry.write({"retention_policy_id": self.policy.id, "retain_until": "2020-01-01 00:00:00"})
        self.assertEqual(
            retention_service.evaluate_record(self.env, entry, self.policy), "pseudonymize"
        )

    def test_evaluate_record_hold_wins_over_expiry(self):
        entry = self._make_entry("held.expired@example.com")
        entry.write({"retention_policy_id": self.policy.id, "retain_until": "2020-01-01 00:00:00"})
        self.env["newsletter.legal.hold"].create(
            {
                "name": "Blocks Expiry",
                "reason": "Preservation",
                "scope_type": "recipient",
                "scope_partner_ids": [(6, 0, [entry.partner_id.id])],
            }
        )
        self.assertEqual(retention_service.evaluate_record(self.env, entry, self.policy), "hold")

    def test_execute_action_dry_run_does_not_mutate(self):
        entry = self._make_entry("dry.run@example.com")
        log = retention_service.execute_action(
            self.env, entry, "pseudonymize", self.policy, dry_run=True
        )
        self.assertEqual(log.dry_run, True)
        self.assertEqual(log.result, "success")
        self.assertEqual(entry.identity_state, "identified")
        self.assertTrue(entry.partner_id)

    def test_execute_action_real_run_pseudonymizes(self):
        entry = self._make_entry("real.run@example.com")
        log = retention_service.execute_action(
            self.env, entry, "pseudonymize", self.policy, dry_run=False
        )
        self.assertEqual(log.dry_run, False)
        self.assertEqual(log.result, "success")
        self.assertEqual(entry.identity_state, "pseudonymized")
        self.assertFalse(entry.partner_id)

    def test_execute_action_logs_are_immutable(self):
        entry = self._make_entry("immutable.log@example.com")
        log = retention_service.execute_action(
            self.env, entry, "pseudonymize", self.policy, dry_run=False
        )
        from odoo.exceptions import UserError

        with self.assertRaises(UserError):
            log.write({"result": "failed"})
        with self.assertRaises(UserError):
            log.unlink()

    def test_process_policy_dry_run_leaves_records_identified(self):
        entry = self._make_entry("process.dry@example.com")
        entry.write({"retention_policy_id": self.policy.id, "retain_until": "2020-01-01 00:00:00"})
        counts = retention_service.process_policy(self.env, self.policy, dry_run=True)
        self.assertEqual(counts.get("pseudonymize"), 1)
        self.assertEqual(entry.identity_state, "identified")

    def test_process_policy_real_run_pseudonymizes_expired_records(self):
        entry = self._make_entry("process.real@example.com")
        entry.write({"retention_policy_id": self.policy.id, "retain_until": "2020-01-01 00:00:00"})
        counts = retention_service.process_policy(self.env, self.policy, dry_run=False)
        self.assertEqual(counts.get("pseudonymize"), 1)
        self.assertEqual(entry.identity_state, "pseudonymized")

    def test_process_policy_skips_records_on_legal_hold(self):
        entry = self._make_entry("process.hold@example.com")
        entry.write({"retention_policy_id": self.policy.id, "retain_until": "2020-01-01 00:00:00"})
        self.env["newsletter.legal.hold"].create(
            {
                "name": "Process Hold Block",
                "reason": "Preservation",
                "scope_type": "recipient",
                "scope_partner_ids": [(6, 0, [entry.partner_id.id])],
            }
        )
        counts = retention_service.process_policy(self.env, self.policy, dry_run=False)
        self.assertEqual(counts.get("hold"), 1)
        self.assertEqual(entry.identity_state, "identified")
        self.assertEqual(entry.retention_state, "on_hold")

    def test_process_policy_unwired_category_is_noop(self):
        unwired_policy = self.env["newsletter.retention.policy"].create(
            {
                "name": "Unwired Category",
                "code": "TEST_UNWIRED_CATEGORY",
                "data_category": "consent_evidence",
                "retention_period_days": 30,
                "expiry_action": "review",
            }
        )
        counts = retention_service.process_policy(self.env, unwired_policy)
        self.assertTrue(counts.get("skipped_no_model"))
