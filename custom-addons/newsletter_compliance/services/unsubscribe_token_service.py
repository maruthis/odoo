"""Signed, stateless tokens for the public one-click unsubscribe link
(R6 blueprint §16.2). The token encodes which partner and which mailing the
link concerns, HMAC-signed with the same secret/machinery as
pseudonymization_service so a link cannot be forged or altered to target a
different recipient.
"""
import base64
import hashlib
import hmac
import json

_TOKEN_SECRET_PARAM = "newsletter_compliance.unsubscribe_token_secret"


def _get_secret(env):
    ICP = env["ir.config_parameter"].sudo()
    secret = ICP.get_param(_TOKEN_SECRET_PARAM)
    if not secret:
        import secrets

        secret = secrets.token_hex(32)
        ICP.set_param(_TOKEN_SECRET_PARAM, secret)
    return secret


def _b64encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data):
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def generate_token(env, partner_id, mailing_id):
    payload = json.dumps({"p": partner_id, "m": mailing_id}, sort_keys=True).encode("utf-8")
    payload_b64 = _b64encode(payload)
    signature = hmac.new(
        _get_secret(env).encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def parse_token(env, token):
    """Returns {"partner_id": int, "mailing_id": int} or None if the token
    is malformed or its signature doesn't match - never raises, since this
    backs a public unauthenticated endpoint.
    """
    if not token or "." not in token:
        return None

    payload_b64, _, signature = token.partition(".")
    expected_signature = hmac.new(
        _get_secret(env).encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64))
        return {"partner_id": int(payload["p"]), "mailing_id": int(payload["m"])}
    except (ValueError, TypeError, KeyError):
        return None
