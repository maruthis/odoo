"""Provider adapter registry.

To add SES/SendGrid/Mailgun, implement NewsletterProviderAdapter in a new
module in this package and register it here - the ingestion pipeline
(controller, cron processor) never needs to change.
"""
from .generic_provider import GenericProviderAdapter
from .mailgun_provider import MailgunProviderAdapter
from .sendgrid_provider import SendGridProviderAdapter
from .ses_provider import SesProviderAdapter
from .smtp_provider import SmtpProviderAdapter

_ADAPTER_CLASSES = {
    "generic": GenericProviderAdapter,
    "smtp": SmtpProviderAdapter,
    "ses": SesProviderAdapter,
    "sendgrid": SendGridProviderAdapter,
    "mailgun": MailgunProviderAdapter,
}


def get_provider_adapter(env, provider_code):
    adapter_class = _ADAPTER_CLASSES.get(provider_code)
    if not adapter_class:
        return None
    return adapter_class(env)


def get_registered_providers():
    return sorted(_ADAPTER_CLASSES.keys())
