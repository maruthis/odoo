"""HMAC-based pseudonymization (R6 section 12-13, 53-54).

Uses HMAC-SHA256 rather than plain SHA-256 specifically so the token
cannot be reversed by dictionary-guessing common email addresses. The
secret is stored in ir.config_parameter, auto-generated on first use if
absent - in a real deployment this should come from a proper secret
manager (Vault, cloud KMS, etc.); the service boundary here is what stays
stable if that's swapped in later.

Key rotation (section 54): CURRENT_TOKEN_VERSION is stamped onto every
token as a prefix ("v1:<hex>"). Rotating the secret means bumping the
version and re-deriving tokens for records still needing to match old
suppressions - matching logic should check the token's own version
against the secret used to verify it, not assume a single global secret
forever.
"""
import hashlib
import hmac
import secrets

CONFIG_PARAM_SECRET = "newsletter_compliance.pseudonymization_secret"
CURRENT_TOKEN_VERSION = "v1"


def _get_secret(env):
    ICP = env["ir.config_parameter"].sudo()
    secret = ICP.get_param(CONFIG_PARAM_SECRET)
    if not secret:
        secret = secrets.token_hex(32)
        ICP.set_param(CONFIG_PARAM_SECRET, secret)
    return secret


def hmac_token(env, value, version=CURRENT_TOKEN_VERSION):
    """Returns a stable "v1:<hex>" token for ``value`` (typically a
    normalized email). Same input + same secret always yields the same
    token, which is exactly what lets a pseudonymized suppression still
    match a re-imported email later.
    """
    secret = _get_secret(env)
    normalized = (value or "").strip().lower()
    digest = hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{version}:{digest}"


def tokens_match(env, value, stored_token):
    if not stored_token or ":" not in stored_token:
        return False
    version = stored_token.split(":", 1)[0]
    return hmac_token(env, value, version=version) == stored_token
