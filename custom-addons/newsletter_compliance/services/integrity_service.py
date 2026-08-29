"""Integrity verification entry point for the audit "Verify Integrity" action.

Delegates to each model's own verify_integrity()/hash logic rather than
duplicating the hash algorithms here, so there is exactly one place that
knows how a given hash is computed. A failure here never triggers a
silent hash recalculation (R6 section 46) - it raises a critical
compliance alert instead, because the discrepancy itself is evidence.
"""


def verify_run_integrity(run, raise_alert_on_failure=True):
    """Verifies the send-event chain, the archive, and the outcome (if
    each exists) for a run."""
    events_ok = run.event_ids.verify_integrity() if run.event_ids else True
    archive_ok = run.archive_id.verify_integrity() if run.archive_id else True
    outcome_ok = run.current_outcome_id.verify_integrity() if run.current_outcome_id else True

    all_ok = events_ok and archive_ok and outcome_ok

    if not all_ok and raise_alert_on_failure:
        run.env["newsletter.compliance.alert"].sudo()._create_or_update_alert(
            "archive_integrity_failure",
            "critical",
            "integrity_check",
            0.0,
            1.0,
            campaign_run=run,
        )

    return {
        "events_ok": events_ok,
        "archive_ok": archive_ok,
        "outcome_ok": outcome_ok,
        "all_ok": all_ok,
    }
