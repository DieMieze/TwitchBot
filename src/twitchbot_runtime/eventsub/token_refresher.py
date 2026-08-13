from __future__ import annotations

from typing import Any

from ..logger import get_logger

logger = get_logger(__name__)


class TokenRefresher:
    """Refreshes a Twitch user access token via ``POST /oauth2/token``.

    On success returns ``(access_token, refresh_token)`` and persists the
    updated pair into ``.env`` via the provided ``TwitchSettings`` instance.
    """

    TOKEN_URL = "https://id.twitch.tv/oauth2/token"

    # --- Member variables ---
    _http: Any | None  # injectable HTTP session (requests.Session by default)

    def __init__(self, http_session: Any | None = None) -> None:
        """
        @brief Construct a TokenRefresher with an optional HTTP session.

        @param http_session: optional pre-configured requests session used for
            the refresh request; when None a new session is lazily created.
        @return: None.
        """
        self._http = http_session

    def _session(self):
        """
        @brief Return the HTTP session, creating one on first use.

        If no session was injected, a new ``requests.Session`` is created and
        cached on the instance for reuse on subsequent calls.

        @return: the active HTTP session used for refresh requests.
        """
        if self._http is not None:
            return self._http
        import requests

        self._http = requests.Session()
        return self._http

    def refresh(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        twitch_settings: Any | None = None,
        prefix: str = "BOT",
    ) -> tuple[str, str] | None:
        """
        @brief Refresh a Twitch user access token using a refresh token.

        Posts the refresh grant to ``/oauth2/token`` and, on success, returns
        the new access/refresh token pair. When a ``TwitchSettings`` instance
        is supplied the new pair is persisted to ``.env`` under the given
        prefix (``BOT`` or ``CHANNEL``).

        @param refresh_token: the current refresh token; empty values abort.
        @param client_id: Twitch application client id.
        @param client_secret: Twitch application client secret.
        @param twitch_settings: optional TwitchSettings instance used to
            persist the refreshed tokens to ``.env``; None skips persistence.
        @param prefix: env var prefix (``BOT`` or ``CHANNEL``) used when
            persisting ``_OAUTH_TOKEN`` / ``_REFRESH_TOKEN``.
        @return: (access_token, refresh_token) tuple on success, or None when
            inputs are missing or the refresh request fails.
        """
        if not refresh_token or not client_id or not client_secret:
            return None
        session = self._session()
        try:
            response = session.post(
                self.TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                timeout=10,
            )
        except Exception:
            logger.exception("Token refresh request failed")
            return None
        if response.status_code != 200:
            logger.info("Token refresh failed: %s %s", response.status_code, getattr(response, "text", ""))
            return None
        try:
            data = response.json()
        except Exception:
            logger.exception("Token refresh returned non-JSON body")
            return None
        access_token = data.get("access_token")
        new_refresh = data.get("refresh_token") or refresh_token
        if not access_token:
            return None
        if twitch_settings is not None:
            try:
                twitch_settings.write_env({
                    f"{prefix}_OAUTH_TOKEN": access_token,
                    f"{prefix}_REFRESH_TOKEN": new_refresh,
                })
            except Exception:
                logger.exception("Failed to persist refreshed token to .env")
        return access_token, new_refresh
