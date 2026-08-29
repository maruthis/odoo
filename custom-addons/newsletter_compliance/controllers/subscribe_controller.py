import logging

from odoo import http
from odoo.http import request

from ..services import subscribe_service

_logger = logging.getLogger(__name__)

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Newsletter Subscription</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:40px auto;">
{body}
</body></html>"""

_FORM_BODY = """
<h2>Newsletter Subscription</h2>
<form method="post" action="/newsletter-compliance/subscribe">
    <p><label>Email*<br/><input type="email" name="email" required="required"/></label></p>
    <p><label>First Name<br/><input type="text" name="first_name"/></label></p>
    <p><label>Last Name<br/><input type="text" name="last_name"/></label></p>
    <p>{purpose_checkboxes}</p>
    <p>Privacy Notice: see each purpose's version above.</p>
    <p><label><input type="checkbox" name="consent" value="1" required="required"/>
       I consent to receiving the selected communications.</label></p>
    <button type="submit">Subscribe</button>
</form>
"""

_PENDING_BODY = """
<h2>Almost done</h2>
<p>We've sent a confirmation link to <strong>{email}</strong>. Please check
your inbox and click the link to activate your subscription.</p>
"""

_INVALID_SUBMISSION_BODY = """
<h2>Please select at least one subscription</h2>
<p><a href="/newsletter-compliance/subscribe">Back to the subscribe form</a></p>
"""

_CONFIRMED_BODY = """
<h2>Subscription confirmed</h2>
<p>You're all set - you'll now receive: <strong>{purposes}</strong></p>
"""

_ALREADY_CONFIRMED_OR_INVALID_BODY = """
<h2>This confirmation link is invalid or already used</h2>
<p>If you believe this is an error, please subscribe again.</p>
"""


class NewsletterSubscribeController(http.Controller):
    @http.route(
        "/newsletter-compliance/subscribe",
        type="http",
        methods=["GET"],
        auth="public",
        csrf=False,
        save_session=False,
    )
    def subscribe_form(self, **kwargs):
        purposes = subscribe_service.get_public_purposes(request.env)
        checkboxes = "".join(
            f'<label><input type="checkbox" name="purpose_ids" value="{p.id}"/> '
            f"{p.name} (Privacy Notice {p.privacy_notice_version})</label><br/>"
            for p in purposes
        )
        body = _FORM_BODY.format(purpose_checkboxes=checkboxes)
        return request.make_response(_PAGE_TEMPLATE.format(body=body))

    @http.route(
        "/newsletter-compliance/subscribe",
        type="http",
        methods=["POST"],
        auth="public",
        csrf=False,
        save_session=False,
    )
    def subscribe_submit(self, email=None, first_name=None, last_name=None, consent=None, **kwargs):
        purpose_ids = [int(v) for v in request.httprequest.form.getlist("purpose_ids")]
        if not email or not consent or not purpose_ids:
            return request.make_response(
                _PAGE_TEMPLATE.format(body=_INVALID_SUBMISSION_BODY), status=400
            )

        partner, records, _token = subscribe_service.submit_request(
            request.env, email, first_name, last_name, purpose_ids
        )
        if not partner:
            return request.make_response(
                _PAGE_TEMPLATE.format(body=_INVALID_SUBMISSION_BODY), status=400
            )

        body = _PENDING_BODY.format(email=partner.email)
        return request.make_response(_PAGE_TEMPLATE.format(body=body))

    @http.route(
        "/newsletter-compliance/subscribe/confirm/<string:token>",
        type="http",
        methods=["GET"],
        auth="public",
        csrf=False,
        save_session=False,
    )
    def subscribe_confirm(self, token, **kwargs):
        activated = subscribe_service.confirm_token(request.env, token)
        if not activated:
            return request.make_response(
                _PAGE_TEMPLATE.format(body=_ALREADY_CONFIRMED_OR_INVALID_BODY), status=400
            )

        purposes = ", ".join(activated.mapped("purpose_id.name"))
        body = _CONFIRMED_BODY.format(purposes=purposes)
        return request.make_response(_PAGE_TEMPLATE.format(body=body))
