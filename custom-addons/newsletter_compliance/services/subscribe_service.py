"""Public subscribe page + double opt-in (Bulk Email blueprint §21-22).

Deliberately mirrors unsubscribe_service.py's shape: plain functions
operating on sudo()'d recordsets, called from a public auth="public"
controller. No dependency on the `website` app - the public page is a
plain HTTP response, the same pattern the unsubscribe controller already
uses successfully, so this stays a self-contained addition to the module
rather than pulling in a whole new app dependency for one form.

Flow:
    submit_request() - creates one PENDING consent record per selected
    purpose, all sharing one confirmation_token, and emails a single
    confirmation link.

    confirm_token() - on click, moves every consent record under that
    token from PENDING to ACTIVE (given_at = now). This is the point a
    purpose-specific consent record actually becomes evidence - never
    created directly as ACTIVE from the public form, so an unconfirmed
    signup can never silently count as consent.
"""
import secrets

from odoo import fields


def _find_or_create_partner(env, email, first_name, last_name):
    email_normalized = (email or "").strip().lower()
    partner = env["res.partner"].sudo().search([("email", "=", email_normalized)], limit=1)
    if partner:
        return partner

    name = " ".join(part for part in (first_name, last_name) if part) or email_normalized
    return env["res.partner"].sudo().create({"name": name, "email": email_normalized})


def get_public_purposes(env):
    return env["newsletter.consent.purpose"].sudo().search(
        [("active", "=", True), ("public_subscribe", "=", True)]
    )


def submit_request(env, email, first_name, last_name, purpose_ids):
    """Creates one PENDING consent record per selected purpose (sharing one
    confirmation token) and returns (partner, consent_records, token).
    Returns (False, empty recordset, False) if no valid purpose was
    selected - callers should treat that as a validation failure.
    """
    purposes = env["newsletter.consent.purpose"].sudo().browse(purpose_ids).filtered(
        lambda p: p.active and p.public_subscribe
    )
    if not purposes:
        return False, env["newsletter.consent.record"], False

    partner = _find_or_create_partner(env, email, first_name, last_name)
    token = secrets.token_urlsafe(32)
    now = fields.Datetime.now()

    records = env["newsletter.consent.record"].sudo()
    for purpose in purposes:
        records |= records.create(
            {
                "partner_id": partner.id,
                "purpose_id": purpose.id,
                "status": "pending",
                "source": "website",
                "channel": "web",
                "privacy_notice_version": purpose.privacy_notice_version,
                "confirmation_token": token,
                "confirmation_requested_at": now,
            }
        )

    _send_confirmation_email(env, partner, records, token)
    return partner, records, token


def _get_default_email_from(env):
    """This flow has no mailing/brand to pull a sender from (a subscriber
    can select purposes spanning several brands) - without an explicit
    email_from, mail.mail.send() raises "mail_from_missing" and the
    confirmation email never even attempts to go out. Same priority chain
    Odoo itself favors: the configured default-from/catchall-domain ICPs,
    then the company's own address, then whichever outgoing mail server
    is actually configured - guaranteed deliverable through it since it's
    the one Odoo will use to send this very message.
    """
    icp = env["ir.config_parameter"].sudo()
    default_from = icp.get_param("mail.default.from")
    catchall_domain = icp.get_param("mail.catchall.domain")
    if default_from and catchall_domain:
        return f"{default_from}@{catchall_domain}"

    if env.company.email:
        return env.company.email

    mail_server = env["ir.mail_server"].sudo().search([], limit=1)
    return mail_server.smtp_user or False


def _send_confirmation_email(env, partner, records, token):
    base_url = env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
    confirm_url = f"{base_url}/newsletter-compliance/subscribe/confirm/{token}"
    purpose_names = ", ".join(records.mapped("purpose_id.name"))

    env["mail.mail"].sudo().create(
        {
            "subject": "Please confirm your subscription",
            "body_html": (
                f"<p>Hello {partner.name or ''},</p>"
                f"<p>Please confirm you want to receive: <strong>{purpose_names}</strong></p>"
                f'<p><a href="{confirm_url}">Confirm subscription</a></p>'
                "<p>If you did not request this, you can ignore this email - "
                "nothing is sent to you until you confirm.</p>"
            ),
            "email_from": _get_default_email_from(env),
            "email_to": partner.email,
            "auto_delete": True,
        }
    ).sudo().send()


def confirm_token(env, token):
    """Activates every pending consent record sharing this token. Returns
    the activated recordset (empty if the token doesn't match any pending
    record - including a token that was already confirmed, so a stale/
    reused confirmation link doesn't error, it just does nothing).
    """
    if not token:
        return env["newsletter.consent.record"]

    pending = env["newsletter.consent.record"].sudo().search(
        [("confirmation_token", "=", token), ("status", "=", "pending")]
    )
    if not pending:
        return pending

    pending.write({"status": "active", "given_at": fields.Datetime.now()})
    return pending
