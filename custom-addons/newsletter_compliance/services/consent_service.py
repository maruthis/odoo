"""Bulk consent lookups for the R3 eligibility engine.

Plain functions rather than an Odoo model: the eligibility engine needs to
resolve consent for thousands of recipients per preflight run, so lookups
are batched (one query per campaign run, not one per recipient).
"""


def get_effective_consents_by_email(env, emails, purpose_id, company_id, evaluation_time):
    """Return {email_normalized: consent_record} for the newest active,
    non-expired consent matching the campaign purpose, for every email that
    has one. Emails without a currently-valid consent are absent from the
    result - callers should fall back to :func:`get_latest_consent_by_email`
    to explain *why* (missing/withdrawn/expired/pending/invalidated).
    """
    if not emails:
        return {}

    domain = [
        ("email_normalized", "in", list(emails)),
        ("purpose_id", "=", purpose_id),
        ("company_id", "=", company_id),
        ("status", "=", "active"),
        ("given_at", "<=", evaluation_time),
        "|",
        ("expires_at", "=", False),
        ("expires_at", ">", evaluation_time),
    ]
    records = env["newsletter.consent.record"].sudo().search(domain, order="given_at desc")

    result = {}
    for record in records:
        # newest wins; flag the data-quality issue rather than silently
        # dropping it (R1 should prevent overlapping active consents, but
        # R3 stays defensive)
        result.setdefault(record.email_normalized, record)
    return result


def get_latest_consent_by_email(env, emails, purpose_id, company_id):
    """Return {email_normalized: consent_record} for the most recent consent
    record of any status, used to explain exclusions when no active consent
    was found (withdrawn/expired/invalidated/pending vs. never given).
    """
    if not emails:
        return {}

    domain = [
        ("email_normalized", "in", list(emails)),
        ("purpose_id", "=", purpose_id),
        ("company_id", "=", company_id),
    ]
    records = env["newsletter.consent.record"].sudo().search(
        domain, order="given_at desc, id desc"
    )

    result = {}
    for record in records:
        result.setdefault(record.email_normalized, record)
    return result
