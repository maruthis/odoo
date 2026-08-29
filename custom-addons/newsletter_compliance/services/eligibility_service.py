"""R3 eligibility engine.

Evaluates a batch of recipient candidates against consent, suppression,
blacklist and mailing-list opt-out state, following the decision order
documented in the R3 spec: cheap deterministic checks (email quality,
duplicates) before the more expensive consent/suppression lookups.

Bulk-fetches blacklist/suppression/consent state for a whole chunk of
recipients at once rather than issuing one query per recipient.
"""
from collections import Counter

from odoo.tools import email_normalize

from . import consent_service, suppression_service

RULESET_VERSION = "1.0"

DEFAULT_BATCH_SIZE = 2000


def _get_blacklisted_emails(env, emails):
    if not emails:
        return set()
    records = env["mail.blacklist"].sudo().search([("email", "in", list(emails))])
    return set(records.mapped("email"))


def evaluate_candidates(env, mailing, campaign_run, candidates, evaluation_time, batch_size=DEFAULT_BATCH_SIZE):
    """Evaluate every candidate and return (eligibility_vals_list, counts).

    ``candidates`` is a list of dicts shaped like::

        {"model": "res.partner", "res_id": 1, "partner_id": 1,
         "mailing_contact_id": False, "email": "a@example.com",
         "mailing_list_ids": [1, 2]}

    ``counts`` is a ``collections.Counter`` keyed by reason_code (including
    "eligible"), used to build the preflight summary and to reconcile
    targeted = eligible + excluded.
    """
    purpose_id = mailing.consent_purpose_id.id
    company_id = env.company.id
    mailing_list_ids = mailing.contact_list_ids.ids

    # Pass 1 (pure python, no DB): normalize/validate/deduplicate.
    resolved = []
    seen_emails = set()
    for candidate in candidates:
        raw_email = candidate.get("email") or ""
        entry = {"candidate": candidate, "email_original": raw_email, "reason_code": None}

        if not raw_email.strip():
            entry["reason_code"] = "missing_email"
            entry["email_normalized"] = ""
        else:
            normalized = email_normalize(raw_email, strict=False)
            if not normalized:
                entry["reason_code"] = "invalid_email"
                entry["email_normalized"] = raw_email.strip().lower()
            elif normalized in seen_emails:
                entry["reason_code"] = "duplicate_email"
                entry["email_normalized"] = normalized
            else:
                seen_emails.add(normalized)
                entry["email_normalized"] = normalized

        resolved.append(entry)

    unique_valid_emails = sorted(seen_emails)

    # Pass 2 (batched DB lookups): blacklist, suppression, consent, opt-out,
    # already-sent - one bulk query per chunk instead of per recipient.
    blacklisted_emails = set()
    suppressions_by_email = {}
    active_consents_by_email = {}

    for i in range(0, len(unique_valid_emails), batch_size):
        chunk = unique_valid_emails[i:i + batch_size]
        blacklisted_emails.update(_get_blacklisted_emails(env, chunk))
        suppressions_by_email.update(
            suppression_service.get_applicable_suppressions_by_email(
                env, chunk, purpose_id, mailing_list_ids, evaluation_time,
                brand_id=mailing.brand_id.id, campaign_mailing_id=mailing.id,
            )
        )
        active_consents_by_email.update(
            consent_service.get_effective_consents_by_email(
                env, chunk, purpose_id, company_id, evaluation_time
            )
        )

    missing_active = [e for e in unique_valid_emails if e not in active_consents_by_email]
    latest_consents_by_email = {}
    for i in range(0, len(missing_active), batch_size):
        chunk = missing_active[i:i + batch_size]
        latest_consents_by_email.update(
            consent_service.get_latest_consent_by_email(env, chunk, purpose_id, company_id)
        )

    opt_out_emails = mailing._get_opt_out_list() or set()
    already_sent_emails = mailing._get_seen_list() or set()

    # Pass 3: finalize status/reason per candidate, in original order (this
    # order becomes evaluation_sequence, used later to resolve which
    # duplicate "wins").
    eligibility_vals_list = []
    counts = Counter()

    for sequence, entry in enumerate(resolved, start=1):
        candidate = entry["candidate"]
        email_normalized = entry["email_normalized"]
        reason_code = entry["reason_code"]
        consent_record = False
        suppression_record = False

        if reason_code is None:
            if email_normalized in blacklisted_emails:
                reason_code = "global_blacklist"
            elif email_normalized in suppressions_by_email:
                suppression_record = suppressions_by_email[email_normalized]
                reason_code = {
                    "global": "global_suppression",
                    "brand": "brand_suppression",
                    "purpose": "purpose_suppression",
                    "mailing_list": "mailing_list_suppression",
                    "campaign": "campaign_suppression",
                }[suppression_record.scope]
            elif email_normalized in opt_out_emails:
                reason_code = "mailing_list_opt_out"
            elif email_normalized in active_consents_by_email:
                consent_record = active_consents_by_email[email_normalized]
                reason_code = (
                    "already_sent" if email_normalized in already_sent_emails else "eligible"
                )
            else:
                latest = latest_consents_by_email.get(email_normalized)
                if not latest:
                    reason_code = "missing_consent"
                elif latest.status == "pending":
                    reason_code = "pending_consent"
                elif latest.status == "withdrawn":
                    reason_code = "withdrawn_consent"
                    consent_record = latest
                elif latest.status == "expired":
                    reason_code = "expired_consent"
                    consent_record = latest
                elif latest.status == "invalidated":
                    reason_code = "invalidated_consent"
                    consent_record = latest
                else:  # superseded, or any other terminal non-active status
                    reason_code = "missing_consent"

        status = "eligible" if reason_code == "eligible" else "excluded"

        eligibility_vals_list.append(
            {
                "campaign_run_id": campaign_run.id,
                "mailing_id": mailing.id,
                "partner_id": candidate.get("partner_id") or False,
                "mailing_contact_id": candidate.get("mailing_contact_id") or False,
                "recipient_model": candidate.get("model"),
                "recipient_res_id": candidate.get("res_id"),
                "email_original": entry["email_original"],
                "email_normalized": email_normalized,
                "status": status,
                "reason_code": reason_code,
                "consent_record_id": consent_record.id if consent_record else False,
                "suppression_entry_id": suppression_record.id if suppression_record else False,
                "mailing_list_id": mailing_list_ids[0] if mailing_list_ids else False,
                "evaluated_at": evaluation_time,
                "ruleset_version": RULESET_VERSION,
                "evaluation_sequence": sequence,
                "company_id": company_id,
            }
        )
        counts[reason_code] += 1

    return eligibility_vals_list, counts
