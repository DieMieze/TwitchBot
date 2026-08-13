from __future__ import annotations

from typing import Any

from ..logger import get_logger

logger = get_logger(__name__)


class AppTokenFetcher:
    """Fetches a Twitch app access token via ``client_credentials`` grant.

    A successful token is cached on the instance for the process lifetime;
    the app token is short-lived (~60 days) and is fetched fresh each start.
    """

    TOKEN_URL = "https://id.twitch.tv/oauth2/token"

    # --- Member variables ---
    _http: Any | None  # injectable HTTP session (requests.Session by default)
    _cached_token: str | None  # cached app access token for the process lifetime

    def __init__(self, http_session: Any | None = None) -> None:
        """
        @brief Construct an AppTokenFetcher with an optional HTTP session.

        @param http_session: optional pre-configured requests session used for
            the token request; when None a new session is lazily created.
        @return: None.
        """
        self._http = http_session
        self._cached_token = None

    def _session(self):
        """
        @brief Return the HTTP session, creating one on first use.

        If no session was injected, a new ``requests.Session`` is created and
        cached on the instance for reuse on subsequent calls.

        @return: the active HTTP session used for token requests.
        """
        if self._http is not None:
            return self._http
        import requests

        self._http = requests.Session()
        return self._http

    def fetch(self, client_id: str, client_secret: str) -> str:
        """
        @brief Fetch a Twitch app access token using the client_credentials grant.

        Returns the cached token if one is already present. Otherwise posts the
        grant to ``/oauth2/token`` and caches the returned ``access_token``.
        Raises ``RuntimeError`` when credentials are missing or Twitch returns
        no token.

        @param client_id: Twitch application client id; required.
        @param client_secret: Twitch application client secret; required.
        @return: the app access token string (cached for the process lifetime).
        """
        if self._cached_token:
            return self._cached_token
        if not client_id or not client_secret:
            raise RuntimeError("Cannot fetch app access token without client_id/secret")
        session = self._session()
        response = session.post(
            self.TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        response.raise_for_status()
        token = response.json().get("access_token", "")
        if not token:
            raise RuntimeError("Twitch did not return an app access token")
        self._cached_token = token
        return token

    @property
    def cached_token(self) -> str | None:
        """
        @brief Return the cached app access token, if any.

        @return: the cached app token string, or None when nothing has been
            fetched yet or the cache was cleared.
        """
        return self._cached_token

    def clear_cache(self) -> None:
        """
        @brief Clear the cached app access token so the next fetch renews it.

        @return: None.
        """
        self._cached_token = None
