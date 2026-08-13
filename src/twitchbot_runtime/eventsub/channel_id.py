from __future__ import annotations

from typing import Any

from ..logger import get_logger

logger = get_logger(__name__)


class ChannelIdFetcher:
    """Resolves a Twitch login to its numeric user id via ``GET /helix/users``."""

    USERS_URL = "https://api.twitch.tv/helix/users"

    # --- Member variables ---
    _http: Any | None  # injectable HTTP session (requests.Session by default)

    def __init__(self, http_session: Any | None = None) -> None:
        """
        @brief Construct a ChannelIdFetcher with an optional HTTP session.

        @param http_session: optional pre-configured requests session used for
            the lookup request; when None a new session is lazily created.
        @return: None.
        """
        self._http = http_session

    def _session(self):
        """
        @brief Return the HTTP session, creating one on first use.

        If no session was injected, a new ``requests.Session`` is created and
        cached on the instance for reuse on subsequent calls.

        @return: the active HTTP session used for user lookup requests.
        """
        if self._http is not None:
            return self._http
        import requests

        self._http = requests.Session()
        return self._http

    def fetch(self, access_token: str, client_id: str, login: str) -> str | None:
        """
        @brief Resolve a Twitch login to its numeric user id.

        Queries ``GET /helix/users`` with the login and returns the first
        matching user's ``id`` string, or ``None`` when inputs are missing, the
        request fails, or no user is returned.

        @param access_token: a valid user/app access token for Helix auth.
        @param client_id: Twitch application client id sent as ``Client-Id``.
        @param login: the Twitch login name to resolve.
        @return: the numeric user id as a string, or None on failure/empty.
        """
        if not access_token or not client_id or not login:
            return None
        session = self._session()
        try:
            response = session.get(
                self.USERS_URL,
                params={"login": login},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": client_id,
                },
                timeout=10,
            )
        except Exception:
            logger.exception("Channel id lookup request failed")
            return None
        if response.status_code != 200:
            logger.info("Channel id lookup failed: %s", response.status_code)
            return None
        try:
            data = response.json()
        except Exception:
            logger.exception("Channel id lookup returned non-JSON body")
            return None
        users = data.get("data") if isinstance(data, dict) else None
        if isinstance(users, list) and users:
            user_id = users[0].get("id")
            if isinstance(user_id, str):
                return user_id
        return None
