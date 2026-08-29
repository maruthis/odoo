"""Campaign run completion determination (R4-BR-10, R4-BR-11)."""

TERMINAL_DISPATCH_STATES = {"sent", "failed", "blocked", "cancelled"}
PENDING_DISPATCH_STATES = {"not_queued", "queued", "processing", "retry_pending"}


def is_complete(eligible_count, state_counts):
    """``state_counts`` is a dict of dispatch_state -> count, covering only
    eligible (status='eligible') recipients. A run is complete when every
    eligible recipient has reached a terminal dispatch state - not merely
    when there's nothing left in the queue this instant.
    """
    pending = sum(state_counts.get(s, 0) for s in PENDING_DISPATCH_STATES)
    return pending == 0


def reconciles(eligible_count, state_counts):
    terminal_total = sum(state_counts.get(s, 0) for s in TERMINAL_DISPATCH_STATES)
    return terminal_total == eligible_count


def classify_completion(state_counts):
    """Returns "completed" or "completed_with_errors". Caller must have
    already confirmed the run is_complete() before calling this - blocked
    recipients alone do not make a run "with errors" (R3/R4: a compliance
    block is correct behavior, not a technical failure).
    """
    if state_counts.get("failed", 0) > 0:
        return "completed_with_errors"
    return "completed"
