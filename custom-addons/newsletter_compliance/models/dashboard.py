import datetime

from odoo import api, fields, models


class NewsletterComplianceDashboard(models.TransientModel):
    _name = "newsletter.compliance.dashboard"
    _description = "Newsletter Compliance Dashboard"

    # -- Campaign Operations -------------------------------------------
    active_runs_count = fields.Integer(compute="_compute_counts")
    retry_pending_count = fields.Integer(compute="_compute_counts")
    failed_recipients_count = fields.Integer(compute="_compute_counts")
    completed_today_count = fields.Integer(compute="_compute_counts")

    # -- Deliverability ---------------------------------------------------
    new_hard_bounces_today_count = fields.Integer(compute="_compute_counts")
    new_complaints_today_count = fields.Integer(compute="_compute_counts")

    # -- Compliance -------------------------------------------------------
    open_alerts_count = fields.Integer(compute="_compute_counts")
    global_suppression_count = fields.Integer(compute="_compute_counts")
    purpose_suppression_count = fields.Integer(compute="_compute_counts")

    # -- Privacy / Retention -------------------------------------------
    records_on_legal_hold_count = fields.Integer(compute="_compute_counts")
    privacy_requests_open_count = fields.Integer(compute="_compute_counts")
    privacy_requests_overdue_count = fields.Integer(compute="_compute_counts")
    retention_failures_count = fields.Integer(compute="_compute_counts")

    def _compute_counts(self):
        env = self.env
        now = fields.Datetime.now()
        today_start = fields.Datetime.to_datetime(fields.Date.today())
        since_yesterday = now - datetime.timedelta(days=1)

        active_runs = env["newsletter.campaign.run"].search_count(
            [("state", "in", ["queued", "sending", "partially_completed"])]
        )
        retry_pending = env["newsletter.recipient.eligibility"].search_count(
            [("dispatch_state", "=", "retry_pending")]
        )
        failed_recipients = env["newsletter.recipient.eligibility"].search_count(
            [("dispatch_state", "=", "failed")]
        )
        completed_today = env["newsletter.campaign.run"].search_count(
            [("state", "=", "archived"), ("execution_completed_at", ">=", today_start)]
        )
        new_hard_bounces = env["newsletter.provider.event"].search_count(
            [("canonical_event_type", "=", "hard_bounce"), ("received_at", ">=", today_start)]
        )
        new_complaints = env["newsletter.provider.event"].search_count(
            [("canonical_event_type", "=", "complaint"), ("received_at", ">=", today_start)]
        )
        open_alerts = env["newsletter.compliance.alert"].search_count([("status", "=", "open")])
        global_suppression = env["newsletter.suppression.entry"].search_count(
            [("scope", "=", "global"), ("active", "=", True)]
        )
        purpose_suppression = env["newsletter.suppression.entry"].search_count(
            [("scope", "=", "purpose"), ("active", "=", True)]
        )
        legal_hold_records = env["newsletter.legal.hold"].search_count([("status", "=", "active")])
        privacy_open = env["newsletter.privacy.request"].search_count(
            [("status", "!=", "completed")]
        )
        privacy_overdue = env["newsletter.privacy.request"].search_count(
            [("status", "!=", "completed"), ("due_at", "<", now)]
        )
        retention_failures = env["newsletter.retention.action"].search_count(
            [("result", "=", "failed"), ("executed_at", ">=", since_yesterday)]
        )

        for dashboard in self:
            dashboard.active_runs_count = active_runs
            dashboard.retry_pending_count = retry_pending
            dashboard.failed_recipients_count = failed_recipients
            dashboard.completed_today_count = completed_today
            dashboard.new_hard_bounces_today_count = new_hard_bounces
            dashboard.new_complaints_today_count = new_complaints
            dashboard.open_alerts_count = open_alerts
            dashboard.global_suppression_count = global_suppression
            dashboard.purpose_suppression_count = purpose_suppression
            dashboard.records_on_legal_hold_count = legal_hold_records
            dashboard.privacy_requests_open_count = privacy_open
            dashboard.privacy_requests_overdue_count = privacy_overdue
            dashboard.retention_failures_count = retention_failures

    @api.model
    def action_open(self):
        record = self.create({})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": record.id,
            "view_mode": "form",
            "target": "current",
        }
