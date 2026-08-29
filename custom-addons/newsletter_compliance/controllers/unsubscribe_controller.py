import logging

from odoo import http
from odoo.http import request

from ..services import unsubscribe_service, unsubscribe_token_service

_logger = logging.getLogger(__name__)

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Unsubscribe</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:40px auto;">
{body}
</body></html>"""

_INVALID_BODY = "<h2>This unsubscribe link is invalid or has expired.</h2>"

_FORM_BODY = """
<h2>Manage your email preferences</h2>
<p>You are unsubscribing <strong>{email}</strong> from <strong>{mailing}</strong>.</p>
<form method="post" action="/newsletter-compliance/unsubscribe/{token}">
    <p><label><input type="radio" name="choice" value="list" checked="checked"/>
       Stop this newsletter only</label></p>
    <p><label><input type="radio" name="choice" value="purpose"/>
       Stop all email for this communication purpose</label></p>
    <p><label><input type="radio" name="choice" value="all"/>
       Stop all marketing email from us</label></p>
    <button type="submit">Confirm</button>
</form>
"""

_CONFIRMATION_BODY = "<h2>You have been unsubscribed.</h2><p>Reference: {reference}</p>"


class NewsletterUnsubscribeController(http.Controller):
    @http.route(
        "/newsletter-compliance/unsubscribe/<string:token>",
        type="http",
        methods=["GET", "POST"],
        auth="public",
        csrf=False,
        save_session=False,
        website=False,
    )
    def unsubscribe(self, token, choice=None, **kwargs):
        env = request.env
        parsed = unsubscribe_token_service.parse_token(env, token)
        if not parsed:
            return request.make_response(_PAGE_TEMPLATE.format(body=_INVALID_BODY), status=400)

        partner = env["res.partner"].sudo().browse(parsed["partner_id"]).exists()
        mailing = env["mailing.mailing"].sudo().browse(parsed["mailing_id"]).exists()
        if not partner or not mailing:
            return request.make_response(_PAGE_TEMPLATE.format(body=_INVALID_BODY), status=400)

        if request.httprequest.method == "GET":
            body = _FORM_BODY.format(
                email=partner.email or partner.name or "",
                mailing=mailing.name or "",
                token=token,
            )
            return request.make_response(_PAGE_TEMPLATE.format(body=body))

        entry = unsubscribe_service.process_choice(env, partner, mailing, choice)
        if not entry:
            return request.make_response(_PAGE_TEMPLATE.format(body=_INVALID_BODY), status=400)

        body = _CONFIRMATION_BODY.format(reference=entry.reference)
        return request.make_response(_PAGE_TEMPLATE.format(body=body))
