import datetime
from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterRetentionFailureMonitor(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.policy = cls.env["newsletter.retention.policy"].create(
            {
                "name": "Monitor Test Policy",
                "code": "MONITOR_TEST_POLICY",
                "data_category": "suppression_history",
                "retention_period_days": 30,
                "expiry_action": "pseudonymize",
            }
        )

    def _create_failed_action(self):
        return self.env["newsletter.retention.action"].create(
            {
                "policy_id": self.policy.id,
                "model_name": "newsletter.suppression.entry",
                "record_reference": "TEST-REF",
                "record_res_id": 1,
                "action_type": "pseudonymize",
                "result": "failed",
                "error_message": "synthetic test failure",
                "company_id": self.env.company.id,
            }
        )

    def test_no_alert_when_no_failures(self):
        self.env["newsletter.retention.action"]._cron_monitor_retention_failures()
        alert = self.env["newsletter.compliance.alert"].search(
            [("alert_type", "=", "retention_failure"), ("status", "=", "open")]
        )
        self.assertFalse(alert)

    def test_alert_raised_when_failures_present(self):
        self._create_failed_action()
        self.env["newsletter.retention.action"]._cron_monitor_retention_failures()
        alert = self.env["newsletter.compliance.alert"].search(
            [("alert_type", "=", "retention_failure"), ("status", "=", "open")]
        )
        self.assertTrue(alert)
        self.assertEqual(alert.metric_value, 1.0)

    def test_alert_severity_escalates_with_more_failures(self):
        for _ in range(5):
            self._create_failed_action()
        self.env["newsletter.retention.action"]._cron_monitor_retention_failures()
        alert = self.env["newsletter.compliance.alert"].search(
            [("alert_type", "=", "retention_failure"), ("status", "=", "open")]
        )
        self.assertEqual(alert.severity, "critical")

    def test_old_failures_outside_lookback_window_are_ignored(self):
        action = self._create_failed_action()
        # Push executed_at outside the 1-day lookback window directly via
        # SQL (the model itself is append-only and blocks write()).
        stale_ts = fields.Datetime.now() - datetime.timedelta(days=5)
        self.env.cr.execute(
            "UPDATE newsletter_retention_action SET executed_at = %s WHERE id = %s",
            (stale_ts, action.id),
        )
        action.invalidate_recordset()

        self.env["newsletter.retention.action"]._cron_monitor_retention_failures()
        alert = self.env["newsletter.compliance.alert"].search(
            [("alert_type", "=", "retention_failure"), ("status", "=", "open")]
        )
        self.assertFalse(alert)


@tagged("post_install", "-at_install")
class TestNewsletterPrivacyRequestOverdueMonitor(TransactionCase):
    def test_no_alert_when_nothing_overdue(self):
        self.env["newsletter.privacy.request"]._cron_monitor_overdue_requests()
        alert = self.env["newsletter.compliance.alert"].search(
            [("alert_type", "=", "privacy_request_overdue"), ("status", "=", "open")]
        )
        self.assertFalse(alert)

    def test_alert_raised_for_overdue_open_request(self):
        request = self.env["newsletter.privacy.request"].create(
            {"request_type": "access", "requester": "Overdue Test Requester"}
        )
        request.write({"received_at": "2020-01-01 00:00:00"})
        self.assertLess(request.due_at, fields.Datetime.now())

        self.env["newsletter.privacy.request"]._cron_monitor_overdue_requests()
        alert = self.env["newsletter.compliance.alert"].search(
            [("alert_type", "=", "privacy_request_overdue"), ("status", "=", "open")]
        )
        self.assertTrue(alert)

    def test_no_alert_for_completed_overdue_request(self):
        request = self.env["newsletter.privacy.request"].create(
            {"request_type": "access", "requester": "Completed Overdue Requester"}
        )
        request.write({"received_at": "2020-01-01 00:00:00", "status": "completed"})

        self.env["newsletter.privacy.request"]._cron_monitor_overdue_requests()
        alert = self.env["newsletter.compliance.alert"].search(
            [("alert_type", "=", "privacy_request_overdue"), ("status", "=", "open")]
        )
        self.assertFalse(alert)


@tagged("post_install", "-at_install")
class TestNewsletterIntegrityVerifierCron(TransactionCase):
    def test_cron_runs_without_error(self):
        # _cron_verify_integrity() commits/rolls back per archived run it
        # finds - correct in production (each run's verification should
        # survive independently of the others), but TransactionCase
        # forbids touching the cursor's commit/rollback directly since it
        # would break the test's own savepoint. Whether any archived runs
        # exist in this database is irrelevant to what this test checks
        # (that the cron entry point doesn't raise), so the commit/
        # rollback calls are stubbed out rather than relied on being
        # unreachable.
        with patch.object(self.env.cr, "commit"), patch.object(self.env.cr, "rollback"):
            self.env["newsletter.campaign.run"]._cron_verify_integrity()
