"""Central retention engine (R6 section 9). Date-math, expiry evaluation,
and action execution all live here rather than scattered across models -
each governed model only needs the newsletter.retention.mixin fields and
one action method (purge_payload/pseudonymize/...).

Only a subset of data categories have an automated processor path wired
up here (provider_raw_event, suppression_history, recipient_eligibility) -
the ones the R6 acceptance tests actually exercise. Categories without an
entry in MODEL_BY_CATEGORY can still have a policy record (for planning/
documentation purposes), they just aren't processed automatically yet;
adding one is a matter of extending the three maps below, not new
architecture.
"""
import datetime
import logging

_logger = logging.getLogger(__name__)

MODEL_BY_CATEGORY = {
    "provider_raw_event": "newsletter.provider.event",
    "suppression_history": "newsletter.suppression.entry",
    "recipient_eligibility": "newsletter.recipient.eligibility",
}

TRIGGER_FIELD_BY_MODEL = {
    "newsletter.provider.event": {
        "record_created": "received_at",
    },
    "newsletter.suppression.entry": {
        "record_created": "effective_from",
        "suppression_reinstated": "reinstated_at",
    },
    "newsletter.recipient.eligibility": {
        "record_created": "evaluated_at",
    },
}


def get_model_name(data_category):
    return MODEL_BY_CATEGORY.get(data_category)


def compute_retain_until(env, policy, record):
    model_name = get_model_name(policy.data_category)
    trigger_field = TRIGGER_FIELD_BY_MODEL.get(model_name, {}).get(policy.retention_trigger)
    if not trigger_field:
        return None

    trigger_ts = record[trigger_field]
    if not trigger_ts:
        return None

    return trigger_ts + datetime.timedelta(days=policy.retention_period_days)


def assign_retention(env, policy, records):
    """Stamps retention_policy_id/retention_start_at/retain_until on each
    record. Idempotent - safe to call repeatedly (e.g. from a cron that
    picks up newly created records under an existing policy).
    """
    for record in records:
        retain_until = compute_retain_until(env, policy, record)
        if not retain_until:
            continue
        record.write(
            {
                "retention_policy_id": policy.id,
                "retention_start_at": fields_now(),
                "retain_until": retain_until,
            }
        )


def fields_now():
    from odoo import fields

    return fields.Datetime.now()


def is_legal_held(env, record):
    """True if any active legal hold covers this record, checked by
    whatever identifying link the record actually has (partner, mailing,
    or campaign run).
    """
    LegalHold = env["newsletter.legal.hold"].sudo()
    active_holds = LegalHold.search([("status", "=", "active")])
    if not active_holds:
        return False

    partner_id = record._fields.get("partner_id") and record.partner_id.id
    if partner_id and active_holds.is_partner_held(partner_id):
        return True

    mailing_id = record._fields.get("mailing_id") and record.mailing_id.id
    if mailing_id and active_holds.is_mailing_held(mailing_id):
        return True

    campaign_run_id = record._fields.get("campaign_run_id") and record.campaign_run_id.id
    if campaign_run_id and active_holds.is_campaign_run_held(campaign_run_id):
        return True

    return bool(active_holds.filtered(lambda h: h.scope_type == "company"))


def evaluate_record(env, record, policy):
    """Returns one of: 'hold', 'skip', 'retain', or the policy's
    expiry_action ('pseudonymize', 'anonymize', 'purge_payload', 'delete',
    'review').
    """
    if is_legal_held(env, record):
        return "hold"

    if not record.retain_until:
        return "skip"

    if record.retain_until > fields_now():
        return "retain"

    return policy.expiry_action


def _hash_record(record):
    import hashlib

    payload = "|".join(f"{k}={v}" for k, v in sorted(record.read()[0].items()) if k != "__last_update")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execute_action(env, record, action, policy, dry_run=False, privacy_request=None):
    """Executes ``action`` on ``record`` (unless dry_run) and always logs
    a newsletter.retention.action row - the log happens whether or not
    anything was actually mutated, so dry-run previews and hold-blocks are
    just as visible as real actions.
    """
    RetentionAction = env["newsletter.retention.action"].sudo()
    before_hash = _hash_record(record) if record.exists() else None
    previous_state = record.retention_state

    result = "success"
    error_message = False
    new_state = previous_state

    try:
        if action == "hold":
            new_state = "on_hold"
            if not dry_run:
                record.write({"retention_state": "on_hold"})
            result = "blocked"

        elif action in ("retain", "skip"):
            return None  # nothing to log - not an expiry decision

        elif action == "review":
            new_state = previous_state

        elif action == "purge_payload":
            new_state = "purged"
            if not dry_run and hasattr(record, "purge_payload"):
                record.purge_payload()

        elif action in ("pseudonymize", "anonymize"):
            new_state = "pseudonymized"
            if not dry_run and hasattr(record, "pseudonymize"):
                record.pseudonymize()

        elif action == "delete":
            new_state = "purged"
            if not dry_run:
                record.unlink()

    except Exception as exc:  # noqa: BLE001
        result = "failed"
        error_message = str(exc)
        _logger.exception("Retention action %s failed for %s", action, record)

    after_hash = _hash_record(record) if not dry_run and record.exists() else before_hash

    return RetentionAction.create(
        {
            "policy_id": policy.id,
            "model_name": record._name,
            "record_reference": record.display_name if record.exists() else "(deleted)",
            "record_res_id": record.id,
            "action_type": action if action != "hold" else "hold_blocked",
            "previous_identity_state": previous_state,
            "new_identity_state": new_state,
            "legal_hold_checked": True,
            "result": result,
            "error_message": error_message,
            "evidence_hash_before": before_hash,
            "evidence_hash_after": after_hash,
            "privacy_request_id": privacy_request.id if privacy_request else False,
            "dry_run": dry_run,
            "company_id": policy.company_id.id,
        }
    )


def process_policy(env, policy, dry_run=None):
    """Processes up to policy.batch_size expired records for one policy.
    dry_run overrides policy.dry_run when explicitly passed (used by the
    preview wizard); otherwise the policy's own flag governs.
    """
    model_name = get_model_name(policy.data_category)
    if not model_name:
        return {"processed": 0, "skipped_no_model": True}

    effective_dry_run = policy.dry_run if dry_run is None else dry_run

    Model = env[model_name].sudo()
    domain = [
        ("retention_policy_id", "=", policy.id),
        ("retain_until", "<=", fields_now()),
        ("retention_state", "not in", ["purged", "on_hold"]),
    ]
    candidates = Model.search(domain, limit=policy.batch_size)

    counts = {"retain": 0, "hold": 0, policy.expiry_action: 0, "failed": 0}
    for record in candidates:
        action = evaluate_record(env, record, policy)
        if action in ("retain", "skip"):
            counts["retain"] = counts.get("retain", 0) + 1
            continue

        log = execute_action(env, record, action, policy, dry_run=effective_dry_run)
        if log and log.result == "failed":
            counts["failed"] = counts.get("failed", 0) + 1
        else:
            counts[action] = counts.get(action, 0) + 1

    return counts
