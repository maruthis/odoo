"""Applies a recipient's self-service unsubscribe choice (R6 blueprint
§16.2). Three effects, matching the blueprint's table exactly:

    newsletter only -> mailing-list opt-out (suppression scoped to the
                        mailing's own list, or its consent purpose if the
                        mailing has no explicit list to scope to)
    purpose         -> withdraw the applicable consent + purpose suppression
    all marketing   -> global suppression (syncs to Odoo's native blacklist
                        via suppression_entry._sync_blacklist)
"""
from odoo import fields, _


def _get_reason(env, code):
    return env["newsletter.suppression.reason"].sudo().search([("code", "=", code)], limit=1)


def _create_suppression(env, partner, vals, reason_code, details):
    reason = _get_reason(env, reason_code)
    base_vals = {
        "partner_id": partner.id,
        "reason_id": reason.id,
        "source": "unsubscribe",
        "details": details,
        "company_id": partner.company_id.id or env.company.id,
    }
    base_vals.update(vals)
    return env["newsletter.suppression.entry"].sudo().create(base_vals)


def unsubscribe_newsletter_only(env, partner, mailing):
    """Mailing-list opt-out - scoped to the specific list driving this
    mailing when one exists; falls back to the mailing's consent purpose
    when the mailing targets recipients by domain rather than a list, since
    there is then no list to scope the suppression to.
    """
    mailing_list = mailing.contact_list_ids[:1]
    if mailing_list:
        return _create_suppression(
            env,
            partner,
            {"scope": "mailing_list", "mailing_list_id": mailing_list.id},
            "UNSUBSCRIBE",
            _("Self-service unsubscribe (newsletter only) via %(mailing)s", mailing=mailing.name),
        )
    return _create_suppression(
        env,
        partner,
        {"scope": "purpose", "purpose_id": mailing.consent_purpose_id.id},
        "UNSUBSCRIBE",
        _(
            "Self-service unsubscribe (newsletter only, no list on mailing - "
            "scoped to purpose) via %(mailing)s",
            mailing=mailing.name,
        ),
    )


def unsubscribe_purpose(env, partner, mailing):
    """Withdraws the partner's active consent for this mailing's purpose
    and creates a matching purpose-scoped suppression.
    """
    purpose = mailing.consent_purpose_id
    active_consents = env["newsletter.consent.record"].sudo().search(
        [
            ("partner_id", "=", partner.id),
            ("purpose_id", "=", purpose.id),
            ("status", "=", "active"),
        ]
    )
    active_consents.write(
        {
            "status": "withdrawn",
            "withdrawn_at": fields.Datetime.now(),
            "withdrawal_reason": _("Self-service unsubscribe"),
            "withdrawal_source": "unsubscribe",
        }
    )
    return _create_suppression(
        env,
        partner,
        {"scope": "purpose", "purpose_id": purpose.id},
        "PURPOSE_OPT_OUT",
        _("Self-service unsubscribe (purpose) via %(mailing)s", mailing=mailing.name),
    )


def unsubscribe_all_marketing(env, partner, mailing):
    """Global suppression - syncs to Odoo's native marketing blacklist."""
    return _create_suppression(
        env,
        partner,
        {"scope": "global"},
        "GLOBAL_OPT_OUT",
        _("Self-service unsubscribe (all marketing) via %(mailing)s", mailing=mailing.name),
    )


CHOICE_HANDLERS = {
    "list": unsubscribe_newsletter_only,
    "purpose": unsubscribe_purpose,
    "all": unsubscribe_all_marketing,
}


def process_choice(env, partner, mailing, choice):
    handler = CHOICE_HANDLERS.get(choice)
    if not handler:
        return None
    return handler(env, partner, mailing)
