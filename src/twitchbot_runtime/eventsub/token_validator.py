from __future__ import annotations

from typing import Any

from ..logger import get_logger

logger = get_logger(__name__)


class TokenValidator:
    """Validates a Twitch OAuth token via ``GET /oauth2/validate``.

    Returns the parsed validation payload (with ``user_id``, ``client_id``,
    ``scopes``, ``expires_in``) on success or ``None`` when the token is
    invalid/unauthorized.
    """

    VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"

    # --- Member variables ---
    _http: Any | None  # injectable HTTP session (requests.Session by default)

    def __init__(self, http_session: Any | None = None) -> None:
        """
        @brief Construct a TokenValidator with an optional HTTP session.

        @param http_session: optional pre-configured requests session used for
            the validate request; when None a new session is lazily created.
        @return: None.
        """
        self._http = http_session

    def _session(self):
        """
        @brief Return the HTTP session, creating one on first use.

        If no session was injected, a new ``requests.Session`` is created and
        cached on the instance so subsequent calls reuse it.

        @return: the active HTTP session used for validation requests.
        """
        if self._http is not None:
            return self._http
        import requests

        self._http = requests.Session()
        return self._http

    def validate(self, token: str) -> dict[str, Any] | None:
        """
        @brief Validate the given OAuth token against Twitch's validate endpoint.

        Sends ``GET /oauth2/validate`` with the token as a Bearer header and
        returns the parsed payload on success, or ``None`` when the token is
        empty, the request fails, or the response is not a JSON dict.

        @param token: the OAuth access token to validate; empty strings are
            rejected without a network call.
        @return: the validation payload dict (with normalized ``scopes`` list)
            on success, or None when validation fails.
        """
        if not token:
            return None
        session = self._session()
        try:
            response = session.get(
                self.VALIDATE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
        except Exception:
            logger.exception("Token validation request failed")
            return None
        if response.status_code != 200:
            logger.info("Token validation failed: %s", response.status_code)
            return None
        try:
            data = response.json()
        except Exception:
            logger.exception("Token validation returned non-JSON body")
            return None
        if not isinstance(data, dict):
            return None
        scopes = data.get("scopes", [])
        if isinstance(scopes, list):
            data["scopes"] = scopes
        else:
            data["scopes"] = []
        return data
