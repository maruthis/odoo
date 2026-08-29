"""Bulk suppression lookups for the R3 eligibility engine.

Precedence (weakest to strongest): campaign < mailing list < purpose <
brand < global. When a recipient matches more than one scope, the
strongest applicable suppression wins, matching the suppression model's
documented precedence rule (Bulk Email blueprint §12: GLOBAL > BRAND >
PURPOSE > MAILING LIST > CAMPAIGN, from broadest to narrowest).

Matches by both email_normalized and email_hash (R6): a suppression entry
that has been pseudonymized has no plain email left, only its HMAC token -
this is what makes "the opt-out survives erasure" actually work end to
end rather than just being a design note.
"""
from . import pseudonymization_service


def get_applicable_suppressions_by_email(
    env, emails, purpose_id, mailing_list_ids, evaluation_time,
    brand_id=False, campaign_mailing_id=False,
):
    """Return {email: suppression_entry} - the strongest applicable active
    suppression for each requested email, across all scopes, matching
    either the plain normalized email or (for pseudonymized entries) its
    HMAC token.

    ``brand_id``/``campaign_mailing_id`` are optional - omitting them
    simply skips the brand/campaign scope checks (e.g. dispatch-time
    rechecks that only have a purpose/list context available).
    """
    if not emails:
        return {}

    emails = list(emails)
    hash_by_email = {email: pseudonymization_service.hmac_token(env, email) for email in emails}
    email_by_hash = {token: email for email, token in hash_by_email.items()}

    base_domain = [
        "|",
        ("email_normalized", "in", emails),
        ("email_hash", "in", list(hash_by_email.values())),
        ("active", "=", True),
        ("effective_from", "<=", evaluation_time),
        "|",
        ("effective_until", "=", False),
        ("effective_until", ">", evaluation_time),
    ]

    campaign_domain = None
    if campaign_mailing_id:
        campaign_domain = base_domain + [
            ("scope", "=", "campaign"),
            ("campaign_mailing_id", "=", campaign_mailing_id),
        ]

    list_domain = None
    if mailing_list_ids:
        list_domain = base_domain + [
            ("scope", "=", "mailing_list"),
            ("mailing_list_id", "in", list(mailing_list_ids)),
        ]

    purpose_domain = None
    if purpose_id:
        purpose_domain = base_domain + [
            ("scope", "=", "purpose"),
            ("purpose_id", "=", purpose_id),
        ]

    brand_domain = None
    if brand_id:
        brand_domain = base_domain + [
            ("scope", "=", "brand"),
            ("brand_id", "=", brand_id),
        ]

    global_domain = base_domain + [("scope", "=", "global")]

    result = {}
    # weakest scope first so a later, stronger scope overwrites it
    for domain in (campaign_domain, list_domain, purpose_domain, brand_domain, global_domain):
        if domain is None:
            continue
        records = env["newsletter.suppression.entry"].sudo().search(domain)
        for record in records:
            matched_email = record.email_normalized or email_by_hash.get(record.email_hash)
            if matched_email:
                result[matched_email] = record

    return result
