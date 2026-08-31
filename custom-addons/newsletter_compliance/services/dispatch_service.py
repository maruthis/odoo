"""Provider-agnostic single-recipient send.

Initially implemented on top of Odoo's own outbound mail infrastructure
(``mail.mail``). A future provider (AWS SES, SendGrid, Mailgun...) can
implement the same ``send_recipient(env, mailing, eligibility)`` contract
without touching the dispatch/retry orchestration in campaign_run.py.

Kept as a plain function (not a model method) specifically so tests can
monkeypatch it directly - real SMTP delivery isn't available in the
dev/test environment, and shouldn't be a dependency of the retry/
resumability logic under test.
"""
import json

from . import retry_service, unsubscribe_token_service


def _build_unsubscribe_url(env, eligibility, mailing):
    if not eligibility.partner_id:
        return False
    base_url = env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
    token = unsubscribe_token_service.generate_token(env, eligibility.partner_id.id, mailing.id)
    return f"{base_url}/newsletter-compliance/unsubscribe/{token}"


def _mailing_trace_document(eligibility):
    """The (model, res_id) mailing.trace needs to point at - mirrors
    mass_mailing's own dual support for a res.partner or mailing.contact
    audience. Returns (False, False) if neither is set (shouldn't happen
    for a frozen eligibility row, but tracking is best-effort - never
    block a send over it).
    """
    if eligibility.partner_id:
        return "res.partner", eligibility.partner_id.id
    if eligibility.mailing_contact_id:
        return "mailing.contact", eligibility.mailing_contact_id.id
    return False, False


def send_recipient(env, mailing, eligibility):
    """Returns a dict:
    {
        "accepted": bool,
        "provider_message_id": str | False,
        "error_code": str | False,
        "error_message": str | False,
        "retryable": bool,
    }
    """
    unsubscribe_url = _build_unsubscribe_url(env, eligibility, mailing)

    # mailing.mail_mail's own _prepare_outgoing_body()/_get_tracking_url()
    # (mass_mailing) only rewrite links into tracked /r/<code> redirects
    # and add the open-tracking pixel when self.mailing_id AND
    # self.mailing_trace_ids are both set at send() time - convert_links()
    # is what actually creates the link.tracker rows those redirects
    # resolve through. Without both of these, "Opened"/"Clicked" on the
    # campaign form can never move off zero, no matter what the recipient
    # does. convert_links() is idempotent per mailing (link.tracker.
    # search_or_create), safe to call once per recipient.
    #
    # mailing.body_html is an Html field, so the ORM hands back a
    # markupsafe.Markup instance - appending a plain f-string to it with
    # += auto-escapes the plain string (Markup.__add__ semantics), which
    # would turn the unsubscribe link into inert escaped text instead of
    # a real <a> tag. str() first so this is a plain string concatenation.
    body_html = str(mailing.convert_links()[mailing.id] or "")
    if unsubscribe_url:
        body_html += (
            f'<p style="font-size:11px;color:#888888;">'
            f'<a href="{unsubscribe_url}">Unsubscribe</a></p>'
        )

    mail_vals = {
        "subject": mailing.subject,
        "body_html": body_html,
        "email_from": mailing.email_from,
        "reply_to": mailing.reply_to or mailing.email_from,
        "email_to": eligibility.email_normalized,
        "auto_delete": True,
        "mailing_id": mailing.id,
    }

    trace_model, trace_res_id = _mailing_trace_document(eligibility)
    if trace_model:
        # Created inline as a one2many command (not a separate
        # mailing.trace.create() call afterwards) so mail.mailing_trace_ids
        # is already populated in-memory before .send() runs its
        # _prepare_outgoing_body() override - the same pattern mass_mailing's
        # own composer uses (wizard/mail_compose_message.py).
        mail_vals["mailing_trace_ids"] = [
            (0, 0, {
                "email": eligibility.email_normalized,
                "mass_mailing_id": mailing.id,
                "model": trace_model,
                "res_id": trace_res_id,
            })
        ]

    if unsubscribe_url:
        # RFC 8058 "one-click" unsubscribe headers - several mailbox
        # providers surface a native unsubscribe action driven by these
        # rather than requiring the recipient to open the message.
        mail_vals["headers"] = json.dumps(
            {
                "List-Unsubscribe": f"<{unsubscribe_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        )

    mail = env["mail.mail"].sudo().create(mail_vals)
    try:
        mail.sudo().send(raise_exception=True)
    except Exception as exc:  # noqa: BLE001 - any send failure is data, not a bug
        error_message = str(exc)
        return {
            "accepted": False,
            "provider_message_id": False,
            "error_code": type(exc).__name__,
            "error_message": error_message,
            "retryable": retry_service.classify_error(error_message),
        }

    return {
        "accepted": True,
        "provider_message_id": str(mail.id),
        "error_code": False,
        "error_message": False,
        "retryable": False,
    }
