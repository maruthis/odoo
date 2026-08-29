"""Builds the campaign audit evidence package (R6 section 37-39, 65).

Produces one consolidated JSON manifest rather than a literal ZIP-of-
files bundle - every section the spec's file list describes (campaign
identity, approvals, preflight, execution, outcome, integrity) is present
as a key in the JSON, which is simpler to generate, hash, and verify
while still being trivially splittable into separate files later if a
real ZIP export is needed.
"""
import hashlib
import json


def _mask_email(email):
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def build_campaign_package(env, run, masked=True):
    from . import integrity_service

    mailing = run.mailing_id
    archive = run.archive_id
    outcome = run.current_outcome_id

    integrity = integrity_service.verify_run_integrity(run)

    package = {
        "campaign": {
            "compliance_campaign_id": mailing.compliance_campaign_id,
            "name": mailing.name,
            "subject": mailing.subject,
            "brand": mailing.brand_id.name,
            "consent_purpose": mailing.consent_purpose_id.name,
        },
        "governance": {
            "governance_version": run.governance_version,
            "approval_version": mailing.approval_version,
            "business_owner": mailing.business_owner_id.name,
        },
        "approvals": [
            {
                "version": entry.approval_version,
                "type": entry.approval_type,
                "decision": entry.decision,
                "reviewer": entry.reviewer_id.name,
                "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
            }
            for entry in mailing.approval_history_ids
        ],
        "preflight": {
            "run_reference": run.reference,
            "targeted_count": run.targeted_count,
            "eligible_count": run.eligible_count,
            "excluded_count": run.excluded_count,
            "result_hash": run.result_hash,
        },
        "execution": {
            "execution_started_at": run.execution_started_at.isoformat() if run.execution_started_at else None,
            "execution_completed_at": run.execution_completed_at.isoformat() if run.execution_completed_at else None,
            "sent_count": run.sent_count,
            "failed_count": run.failed_count,
            "blocked_at_dispatch_count": run.blocked_at_dispatch_count,
            "cancelled_count": run.cancelled_count,
        },
        "outcome": {
            "delivered_count": outcome.delivered_count if outcome else None,
            "soft_bounced_count": outcome.soft_bounced_count if outcome else None,
            "hard_bounced_count": outcome.hard_bounced_count if outcome else None,
            "complained_count": outcome.complained_count if outcome else None,
            "unsubscribed_count": outcome.unsubscribed_count if outcome else None,
            "outcome_hash": outcome.outcome_hash if outcome else None,
        } if outcome else None,
        "integrity": {
            "archive_hash": archive.archive_hash if archive else None,
            "archive_hash_valid": integrity["archive_ok"],
            "send_event_chain_valid": integrity["events_ok"],
        },
    }

    if masked and archive:
        package["campaign"]["email_from"] = _mask_email(archive.email_from_snapshot)
    elif archive:
        package["campaign"]["email_from"] = archive.email_from_snapshot

    encoded = json.dumps(package, sort_keys=True, default=str).encode("utf-8")
    file_hash = hashlib.sha256(encoded).hexdigest()

    return package, file_hash


def build_recipient_package(env, discovery_manifest, masked=True):
    """R6 section 40: one recipient's full timeline across R1-R5."""

    def _fmt_email(email):
        return _mask_email(email) if masked else email

    package = {
        "consent_records": [
            {
                "reference": c.reference,
                "purpose": c.purpose_id.name,
                "status": c.status,
                "given_at": c.given_at.isoformat() if c.given_at else None,
                "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
            }
            for c in discovery_manifest["consent_records"]
        ],
        "suppression_entries": [
            {
                "reference": s.reference,
                "scope": s.scope,
                "reason": s.reason_id.code,
                "effective_from": s.effective_from.isoformat() if s.effective_from else None,
                "active": s.active,
            }
            for s in discovery_manifest["suppression_entries"]
        ],
        "eligibility_decisions": [
            {
                "campaign_run": e.campaign_run_id.reference,
                "status": e.status,
                "reason_code": e.reason_code,
                "dispatch_state": e.dispatch_state,
                "delivery_state": e.delivery_state,
                "email": _fmt_email(e.email_normalized),
            }
            for e in discovery_manifest["eligibility_decisions"]
        ],
        "send_events": [
            {
                "reference": ev.reference,
                "event_type": ev.event_type,
                "event_timestamp": ev.event_timestamp.isoformat() if ev.event_timestamp else None,
            }
            for ev in discovery_manifest["send_events"]
        ],
    }

    encoded = json.dumps(package, sort_keys=True, default=str).encode("utf-8")
    file_hash = hashlib.sha256(encoded).hexdigest()
    return package, file_hash
