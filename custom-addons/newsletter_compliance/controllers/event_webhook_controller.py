import json
import logging

from odoo import http
from odoo.http import request

from ..services.providers import registry

_logger = logging.getLogger(__name__)


class NewsletterEventWebhookController(http.Controller):
    @http.route(
        "/newsletter-compliance/v1/events/<string:provider>",
        type="http",
        methods=["POST"],
        auth="public",
        csrf=False,
        save_session=False,
    )
    def receive_provider_event(self, provider, **kwargs):
        """Fast, reliable webhook endpoint (R5 section 7): authenticate,
        persist the raw event, return 2xx immediately. All downstream
        classification/suppression/alerting happens later via the
        provider-event processing cron - never inline in this request.
        """
        body = request.httprequest.get_data()
        headers = request.httprequest.headers

        adapter = registry.get_provider_adapter(request.env, provider)
        if not adapter:
            return request.make_json_response({"error": "unknown provider"}, status=404)

        if not adapter.validate_webhook(headers, body):
            _logger.warning("Rejected unauthenticated webhook for provider %s", provider)
            return request.make_json_response({"error": "unauthorized"}, status=401)

        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            _logger.warning("Rejected malformed webhook payload for provider %s", provider)
            return request.make_json_response({"error": "invalid payload"}, status=400)

        try:
            canonical_events = adapter.normalize_event(payload)
        except Exception:
            _logger.exception("Failed to normalize webhook payload for provider %s", provider)
            return request.make_json_response({"error": "invalid payload"}, status=400)

        ProviderEvent = request.env["newsletter.provider.event"].sudo()
        accepted = 0
        for canonical_event in canonical_events:
            ProviderEvent.ingest(provider, canonical_event)
            accepted += 1

        return request.make_json_response({"accepted": accepted}, status=200)
