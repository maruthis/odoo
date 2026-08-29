"""Deliverability/reputation policy configuration.

Backed by ir.config_parameter (same pattern as R3's preflight batch size)
rather than a bespoke persistent settings model - exposed to admins via a
res.config.settings extension.
"""

_DEFAULTS = {
    "newsletter_compliance.soft_bounce_threshold": "3",
    "newsletter_compliance.soft_bounce_window_days": "90",
    "newsletter_compliance.bounce_warning_rate": "0.02",
    "newsletter_compliance.bounce_critical_rate": "0.05",
    "newsletter_compliance.complaint_warning_rate": "0.0005",
    "newsletter_compliance.complaint_critical_rate": "0.001",
    "newsletter_compliance.unsubscribe_warning_rate": "0.02",
    "newsletter_compliance.auto_suspend_on_critical": "True",
    "newsletter_compliance.outcome_finalization_window_hours": "72",
    "newsletter_compliance.event_processing_retry_limit": "5",
    "newsletter_compliance.minimum_eligible_recipient_count": "1",
    "newsletter_compliance.max_preflight_age_minutes": "1440",
    "newsletter_compliance.dispatch_batch_size": "500",
    "newsletter_compliance.maximum_retry_count": "5",
    "newsletter_compliance.base_retry_delay_seconds": "60",
    "newsletter_compliance.maximum_retry_delay_seconds": "3600",
    "newsletter_compliance.retention_batch_size": "1000",
    "newsletter_compliance.retention_dry_run_default": "True",
    "newsletter_compliance.audit_export_expiry_days": "7",
}


def _get_param(env, key):
    # get_param returns False (not None/"") when the parameter has never
    # been set - and False is not in (None, ""), so that sentinel must be
    # checked explicitly or the fallback below never triggers.
    value = env["ir.config_parameter"].sudo().get_param(key)
    return value if value else _DEFAULTS[key]


def get_soft_bounce_threshold(env):
    return int(_get_param(env, "newsletter_compliance.soft_bounce_threshold"))


def get_soft_bounce_window_days(env):
    return int(_get_param(env, "newsletter_compliance.soft_bounce_window_days"))


def get_bounce_warning_rate(env):
    return float(_get_param(env, "newsletter_compliance.bounce_warning_rate"))


def get_bounce_critical_rate(env):
    return float(_get_param(env, "newsletter_compliance.bounce_critical_rate"))


def get_complaint_warning_rate(env):
    return float(_get_param(env, "newsletter_compliance.complaint_warning_rate"))


def get_complaint_critical_rate(env):
    return float(_get_param(env, "newsletter_compliance.complaint_critical_rate"))


def get_unsubscribe_warning_rate(env):
    return float(_get_param(env, "newsletter_compliance.unsubscribe_warning_rate"))


def get_auto_suspend_on_critical(env):
    return _get_param(env, "newsletter_compliance.auto_suspend_on_critical") == "True"


def get_outcome_finalization_window_hours(env):
    return int(_get_param(env, "newsletter_compliance.outcome_finalization_window_hours"))


def get_event_processing_retry_limit(env):
    return int(_get_param(env, "newsletter_compliance.event_processing_retry_limit"))


def get_minimum_eligible_recipient_count(env):
    return int(_get_param(env, "newsletter_compliance.minimum_eligible_recipient_count"))


def get_max_preflight_age_minutes(env):
    return int(_get_param(env, "newsletter_compliance.max_preflight_age_minutes"))


def get_dispatch_batch_size(env):
    return int(_get_param(env, "newsletter_compliance.dispatch_batch_size"))


def get_maximum_retry_count(env):
    return int(_get_param(env, "newsletter_compliance.maximum_retry_count"))


def get_base_retry_delay_seconds(env):
    return int(_get_param(env, "newsletter_compliance.base_retry_delay_seconds"))


def get_maximum_retry_delay_seconds(env):
    return int(_get_param(env, "newsletter_compliance.maximum_retry_delay_seconds"))


def get_retention_batch_size(env):
    return int(_get_param(env, "newsletter_compliance.retention_batch_size"))


def get_retention_dry_run_default(env):
    return _get_param(env, "newsletter_compliance.retention_dry_run_default") == "True"


def get_audit_export_expiry_days(env):
    return int(_get_param(env, "newsletter_compliance.audit_export_expiry_days"))
