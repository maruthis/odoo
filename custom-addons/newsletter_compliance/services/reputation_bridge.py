"""Bridges provider-event processing to reputation, suppression, and
alerting - the R5 side of the "SEND -> OUTCOME -> LEARN -> SUPPRESS"
feedback loop. Kept as an orchestration service (not model methods)
because it coordinates across several models: reputation, suppression,
outcome, and alerts.
"""
from odoo import _

from . import config_service

_REASON_SOURCE_MAP = {
    "HARD_BOUNCE": "bounce",
    "SOFT_BOUNCE_LIMIT": "bounce",
    "COMPLAINT": "complaint",
    "GLOBAL_OPT_OUT": "unsubscribe",
}


def _create_global_suppression(env, eligibility, reason_code, send_event=None):
    if not eligibility.partner_id:
        return None

    reason = env["newsletter.suppression.reason"].sudo().search(
        [("code", "=", reason_code)], limit=1
    )
    if not reason:
        return None

    existing = env["newsletter.suppression.entry"].sudo().search(
        [
            ("partner_id", "=", eligibility.partner_id.id),
            ("scope", "=", "global"),
            ("reason_id", "=", reason.id),
            ("active", "=", True),
        ],
        limit=1,
    )
    if existing:
        return existing

    vals = {
        "partner_id": eligibility.partner_id.id,
        "scope": "global",
        "reason_id": reason.id,
        "source": _REASON_SOURCE_MAP.get(reason_code, "other"),
    }
    if send_event:
        vals["source_event_id"] = send_event.id
        vals["provider_event_id"] = send_event.provider_event_id

    return env["newsletter.suppression.entry"].sudo().create(vals)


def apply_delivered(env, eligibility, event_timestamp):
    reputation = env["newsletter.delivery.reputation"]._get_or_create(
        eligibility.email_normalized, eligibility.partner_id.id, eligibility.company_id.id
    )
    reputation.record_delivered(event_timestamp)


def apply_bounce(env, eligibility, classification, event_timestamp, send_event=None):
    reputation = env["newsletter.delivery.reputation"]._get_or_create(
        eligibility.email_normalized, eligibility.partner_id.id, eligibility.company_id.id
    )

    if classification == "hard":
        reputation.record_hard_bounce(event_timestamp)
        _create_global_suppression(env, eligibility, "HARD_BOUNCE", send_event)
    elif classification == "soft":
        threshold = config_service.get_soft_bounce_threshold(env)
        window_days = config_service.get_soft_bounce_window_days(env)
        new_count = reputation.record_soft_bounce(event_timestamp, window_days)
        if new_count >= threshold:
            _create_global_suppression(env, eligibility, "SOFT_BOUNCE_LIMIT", send_event)
    # classification == "unknown": recorded on the recipient/reputation
    # already via delivery_state, but never auto-suppressed - conservative
    # by design (R5 section 29).


def apply_complaint(env, eligibility, event_timestamp, send_event=None):
    reputation = env["newsletter.delivery.reputation"]._get_or_create(
        eligibility.email_normalized, eligibility.partner_id.id, eligibility.company_id.id
    )
    reputation.record_complaint(event_timestamp)
    _create_global_suppression(env, eligibility, "COMPLAINT", send_event)


def apply_unsubscribe(env, eligibility, send_event=None):
    _create_global_suppression(env, eligibility, "GLOBAL_OPT_OUT", send_event)


def evaluate_run_alerts(env, run):
    if not run or not run.current_outcome_id:
        return

    outcome = run.sudo().current_outcome_id
    Alert = env["newsletter.compliance.alert"]

    bounce_warning = config_service.get_bounce_warning_rate(env)
    bounce_critical = config_service.get_bounce_critical_rate(env)
    complaint_warning = config_service.get_complaint_warning_rate(env)
    complaint_critical = config_service.get_complaint_critical_rate(env)

    bounce_rate = outcome.bounce_rate
    complaint_rate = outcome.complaint_rate

    new_threshold_state = "healthy"

    if bounce_rate >= bounce_critical and bounce_critical > 0:
        Alert._create_or_update_alert(
            "bounce_threshold", "critical", "bounce_rate", bounce_rate, bounce_critical,
            campaign_run=run,
        )
        new_threshold_state = "critical"
        if config_service.get_auto_suspend_on_critical(env) and run.state in (
            "queued", "sending", "partially_completed",
        ):
            run.sudo().action_suspend(
                reason=_("Auto-suspended: bounce rate exceeded the critical threshold.")
            )
    elif bounce_rate >= bounce_warning and bounce_warning > 0:
        Alert._create_or_update_alert(
            "bounce_threshold", "warning", "bounce_rate", bounce_rate, bounce_warning,
            campaign_run=run,
        )
        new_threshold_state = "warning"

    if complaint_rate >= complaint_critical and complaint_critical > 0:
        Alert._create_or_update_alert(
            "complaint_threshold", "critical", "complaint_rate", complaint_rate,
            complaint_critical, campaign_run=run,
        )
        new_threshold_state = "critical"
        if config_service.get_auto_suspend_on_critical(env) and run.state in (
            "queued", "sending", "partially_completed",
        ):
            run.sudo().action_suspend(
                reason=_("Auto-suspended: complaint rate exceeded the critical threshold.")
            )
    elif complaint_rate >= complaint_warning and complaint_warning > 0:
        Alert._create_or_update_alert(
            "complaint_threshold", "warning", "complaint_rate", complaint_rate,
            complaint_warning, campaign_run=run,
        )
        if new_threshold_state != "critical":
            new_threshold_state = "warning"

    if new_threshold_state != outcome.threshold_state:
        outcome.sudo().write({"threshold_state": new_threshold_state})
