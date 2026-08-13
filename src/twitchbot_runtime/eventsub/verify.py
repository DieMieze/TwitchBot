from __future__ import annotations

import hashlib
import hmac
from typing import Any

MAX_TIMESTAMP_SKEW_SECONDS = 600


def verify_signature(
    message_id: str,
    message_timestamp: str,
    body: str,
    secret: str,
    signature_header: str,
    *,
    now: float | None = None,
    max_skew_seconds: int = MAX_TIMESTAMP_SKEW_SECONDS,
) -> bool:
    """Verify a Twitch EventSub webhook signature.

    Twitch sends ``Twitch-Eventsub-Message-Id``, ``Twitch-Eventsub-Message-Timestamp``
    headers and a ``Twitch-Eventsub-Message-Signature`` header of the form
    ``sha256=<hex>``. The HMAC is computed over
    ``message_id + message_timestamp + body`` with the shared webhook secret.
    """
    if not secret or not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False
    provided = signature_header[len("sha256="):]

    if now is not None:
        try:
            timestamp_value = float(message_timestamp)
        except (TypeError, ValueError):
            return False
        if abs(now - timestamp_value) > max_skew_seconds:
            return False

    hmac_message = f"{message_id}{message_timestamp}{body}".encode()
    expected = hmac.new(
        secret.encode("utf-8"),
        hmac_message,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, provided.lower())


def is_challenge_request(headers: dict[str, Any], body: Any) -> bool:
    message_type = _header(headers, "Twitch-Eventsub-Message-Type")
    return str(message_type).lower() == "webhook_callback_verification"


def extract_challenge(body: Any) -> str | None:
    if isinstance(body, dict):
        challenge = body.get("challenge")
        if isinstance(challenge, str):
            return challenge
    return None


def _header(headers: dict[str, Any], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return ""
