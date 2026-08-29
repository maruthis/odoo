from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNewsletterComplianceDashboard(TransactionCase):
    def test_action_open_creates_and_returns_form_action(self):
        Dashboard = self.env["newsletter.compliance.dashboard"]
        action = Dashboard.action_open()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "newsletter.compliance.dashboard")
        self.assertTrue(action["res_id"])

    def test_counts_reflect_open_alerts(self):
        Dashboard = self.env["newsletter.compliance.dashboard"]
        before = Dashboard.create({})
        baseline = before.open_alerts_count

        self.env["newsletter.compliance.alert"].create(
            {
                "alert_type": "reputation_risk",
                "severity": "warning",
                "metric_name": "test_metric",
                "metric_value": 1.0,
                "threshold_value": 0.5,
            }
        )

        after = Dashboard.create({})
        self.assertEqual(after.open_alerts_count, baseline + 1)

    def test_counts_reflect_active_legal_holds(self):
        Dashboard = self.env["newsletter.compliance.dashboard"]
        before = Dashboard.create({})
        baseline = before.records_on_legal_hold_count

        self.env["newsletter.legal.hold"].create(
            {
                "name": "Dashboard Test Hold",
                "reason": "Testing dashboard counts",
                "scope_type": "company",
            }
        )

        after = Dashboard.create({})
        self.assertEqual(after.records_on_legal_hold_count, baseline + 1)

    def test_counts_reflect_open_privacy_requests(self):
        Dashboard = self.env["newsletter.compliance.dashboard"]
        before = Dashboard.create({})
        baseline_open = before.privacy_requests_open_count

        self.env["newsletter.privacy.request"].create(
            {"request_type": "access", "requester": "Dashboard Test Requester"}
        )

        after = Dashboard.create({})
        self.assertEqual(after.privacy_requests_open_count, baseline_open + 1)
