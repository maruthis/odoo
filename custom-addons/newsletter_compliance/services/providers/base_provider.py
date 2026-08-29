"""Provider adapter contract (R5 section 65).

The compliance layer only ever operates on a CanonicalDeliveryEvent -
never on provider-specific payload shapes or event names. Each concrete
provider adapter is responsible for translating its own webhook payload
and authentication scheme into this canonical shape.
"""
from dataclasses import dataclass, field
from typing import Optional

CANONICAL_EVENT_TYPES = {
    "accepted",
    "delivered",
    "delivery_delayed",
    "soft_bounce",
    "hard_bounce",
    "complaint",
    "unsubscribe",
    "provider_rejected",
    "provider_dropped",
    "unknown",
}


@dataclass
class CanonicalDeliveryEvent:
    provider: str
    provider_event_id: str
    provider_message_id: Optional[str]
    event_type: str
    event_timestamp: str
    email: Optional[str] = None
    bounce_type: Optional[str] = None
    bounce_subtype: Optional[str] = None
    smtp_status: Optional[str] = None
    diagnostic_code: Optional[str] = None
    raw_payload: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.event_type not in CANONICAL_EVENT_TYPES:
            self.event_type = "unknown"


class NewsletterProviderAdapter:
    """Base class for a provider integration. Subclass and register in
    ``registry.PROVIDER_ADAPTERS`` to add a new provider.
    """

    provider_code = None

    def validate_webhook(self, headers, body):
        """Return True if the inbound request is authentic. Must not raise
        for a routine invalid signature - return False so the controller
        can respond with 401/403 without leaking details.
        """
        raise NotImplementedError

    def normalize_event(self, payload):
        """Return a CanonicalDeliveryEvent (or a list of them - some
        providers batch multiple events per webhook call)."""
        raise NotImplementedError

    def classify_bounce(self, canonical_event):
        """Return one of 'hard', 'soft', 'unknown' for a bounce-type
        canonical event. Conservative by default: unknown unless the
        adapter can say for certain.
        """
        return "unknown"

    def extract_message_id(self, canonical_event):
        return canonical_event.provider_message_id

    def extract_event_id(self, canonical_event):
        return canonical_event.provider_event_id
