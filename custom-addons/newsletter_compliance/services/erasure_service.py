"""Executes an erasure/restriction decision against a discovery manifest
(R6 section 23, 55, 64). Never a blind DELETE: every item is evaluated
individually, legal hold always wins, and categories that must remain as
regulatory/audit evidence (consent records, send events, provider events,
reputation) are explicitly retained with a stated reason rather than
erased - only suppression entries and eligibility decisions (the two
categories with a real pseudonymize() implementation) are actually
de-identified. This matches R6-BR-05: erasure must not silently delete
audit/regulatory evidence.
"""
from . import retention_service


def determine_action(env, record):
    if retention_service.is_legal_held(env, record):
        return "retained_legal_hold"
    return "pseudonymize" if hasattr(record, "pseudonymize") else "retained_audit_evidence"


def execute(env, manifest, privacy_request=None):
    """Returns a list of {model, record_id, action, result} dicts, and
    creates one newsletter.retention.action log entry per record acted
    upon (or explicitly retained), so a completed erasure request always
    has a full accounting of what happened to every discovered record.
    """
    RetentionAction = env["newsletter.retention.action"].sudo()
    results = []

    for category, records in manifest.items():
        for record in records:
            action = determine_action(env, record)

            if action == "pseudonymize":
                before_state = record.retention_state if "retention_state" in record._fields else "identified"
                record.pseudonymize()
                result = "success"
                new_state = "pseudonymized"
                action_type = "pseudonymize"
            elif action == "retained_legal_hold":
                result = "blocked"
                before_state = "identified"
                new_state = "on_hold"
                action_type = "hold_blocked"
            else:
                result = "success"
                before_state = "identified"
                new_state = "identified"
                action_type = "retain"

            RetentionAction.create(
                {
                    "model_name": record._name,
                    "record_reference": record.display_name,
                    "record_res_id": record.id,
                    "action_type": action_type,
                    "previous_identity_state": before_state,
                    "new_identity_state": new_state,
                    "legal_hold_checked": True,
                    "result": result,
                    "privacy_request_id": privacy_request.id if privacy_request else False,
                    "company_id": env.company.id,
                }
            )

            results.append(
                {"category": category, "model": record._name, "record_id": record.id, "action": action}
            )

    return results
