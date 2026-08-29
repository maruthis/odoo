"""Given a subject (partner and/or normalized email), finds every
compliance record that concerns them, across R1-R5 models (R6 section
24-25). Searches by partner_id, normalized email, and pseudonymization
hash, since the same person may show up as a res.partner, a mailing
contact, or only as a suppression token after an earlier erasure (R6
section 57).
"""
from . import pseudonymization_service


def discover(env, partner=None, email_normalized=None):
    email_normalized = (email_normalized or (partner.email if partner else "") or "").strip().lower()
    email_hash = pseudonymization_service.hmac_token(env, email_normalized) if email_normalized else False

    partner_domain = [("partner_id", "=", partner.id)] if partner else []

    consents = env["newsletter.consent.record"].sudo()
    if partner:
        consents = consents.search([("partner_id", "=", partner.id)])

    suppressions = env["newsletter.suppression.entry"].sudo()
    supp_domain = []
    if partner:
        supp_domain = ["|", ("partner_id", "=", partner.id), ("email_hash", "=", email_hash)]
    elif email_hash:
        supp_domain = [("email_hash", "=", email_hash)]
    if supp_domain:
        suppressions = suppressions.search(supp_domain)

    eligibility = env["newsletter.recipient.eligibility"].sudo()
    if partner:
        eligibility = eligibility.search([("partner_id", "=", partner.id)])
    elif email_normalized:
        eligibility = eligibility.search([("email_normalized", "=", email_normalized)])

    send_events = env["newsletter.send.event"].sudo()
    if partner:
        send_events = send_events.search([("partner_id", "=", partner.id)])
    elif email_normalized:
        send_events = send_events.search([("email_normalized", "=", email_normalized)])

    provider_events = env["newsletter.provider.event"].sudo()
    if eligibility:
        provider_events = provider_events.search([("eligibility_id", "in", eligibility.ids)])
    elif email_normalized:
        provider_events = provider_events.search([("canonical_email", "=", email_normalized)])

    reputation = env["newsletter.delivery.reputation"].sudo()
    if email_normalized:
        reputation = reputation.search([("email_normalized", "=", email_normalized)])
    elif partner:
        reputation = reputation.search([("partner_id", "=", partner.id)])

    manifest = {
        "consent_records": consents,
        "suppression_entries": suppressions,
        "eligibility_decisions": eligibility,
        "send_events": send_events,
        "provider_events": provider_events,
        "reputation": reputation,
    }

    counts = {key: len(recordset) for key, recordset in manifest.items()}

    return {"manifest": manifest, "counts": counts}
