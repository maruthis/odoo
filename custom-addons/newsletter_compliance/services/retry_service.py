"""Retry classification and exponential backoff for R4 dispatch execution."""

BASE_RETRY_DELAY_SECONDS = 60
MAXIMUM_RETRY_DELAY_SECONDS = 3600
DEFAULT_MAXIMUM_RETRY_COUNT = 5

# Heuristic classification of common SMTP/connection failure signatures.
# Anything not recognized defaults to non-retryable, since silently
# retrying an unrecognized permanent error indefinitely is worse than
# surfacing it as a failure for a human to look at.
_RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "temporarily",
    "temporary",
    "connection",
    "421",
    "450",
    "451",
    "452",
    "rate limit",
    "throttle",
    "unavailable",
)

_NON_RETRYABLE_MARKERS = (
    "550",
    "551",
    "552",
    "553",
    "554",
    "invalid",
    "malformed",
    "rejected",
    "not authorized",
    "authentication",
)


def classify_error(error_message):
    """Classify a raw error string as retryable or not. Compliance blocks
    are classified separately by the caller (they're not technical errors
    at all), so this only distinguishes retryable vs. non-retryable.
    """
    text = (error_message or "").lower()

    for marker in _NON_RETRYABLE_MARKERS:
        if marker in text:
            return False

    for marker in _RETRYABLE_MARKERS:
        if marker in text:
            return True

    return False


def calculate_next_retry_delay(attempt_number, base_delay=BASE_RETRY_DELAY_SECONDS, max_delay=MAXIMUM_RETRY_DELAY_SECONDS):
    """attempt_number is 1-indexed (the attempt that just failed)."""
    delay = base_delay * (2 ** max(attempt_number - 1, 0))
    return min(delay, max_delay)
