from __future__ import annotations

import threading
from typing import Any

from ..logger import get_logger
from ..twitch_settings import BOT_SCOPES, CHANNEL_SCOPES

logger = get_logger(__name__)

DEFAULT_REDIRECT_URI = "http://localhost:5003/oauth/callback"
DEFAULT_OAUTH_PORT = 5003

AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


class OAuthFlowStarter:
    """Builds Twitch OAuth authorize URLs and exchanges the returned code
    for an ``(access_token, refresh_token)`` pair.

    ``start_and_wait`` runs a tiny one-shot Flask server on port 5003 to
    receive the OAuth redirect. If Flask is unavailable or the port is busy,
    falls back to a terminal prompt asking the user to paste the code.
    """

    # --- Member variables ---
    _http: Any | None  # injectable HTTP session (requests.Session by default)

    def __init__(self, http_session: Any | None = None) -> None:
        """
        @brief Construct an OAuthFlowStarter with an optional HTTP session.

        @param http_session: optional pre-configured requests session used for
            the code-exchange request; when None a new session is lazily
            created.
        @return: None.
        """
        self._http = http_session

    def _session(self):
        """
        @brief Return the HTTP session, creating one on first use.

        If no session was injected, a new ``requests.Session`` is created and
        cached on the instance for reuse on subsequent calls.

        @return: the active HTTP session used for token exchange requests.
        """
        if self._http is not None:
            return self._http
        import requests

        self._http = requests.Session()
        return self._http

    @staticmethod
    def build_url(client_id: str, scopes: list[str], redirect_uri: str = DEFAULT_REDIRECT_URI, state: str = "twitchbot") -> str:
        """
        @brief Build a Twitch OAuth authorize URL for the given scopes.

        Constructs the ``GET /oauth2/authorize`` URL with response_type=code,
        the supplied client id, redirect uri, space-joined scopes, and state.

        @param client_id: Twitch application client id to embed in the URL.
        @param scopes: list of OAuth scope strings to request.
        @param redirect_uri: the redirect URI registered for the app.
        @param state: opaque state value echoed back in the callback.
        @return: the fully-formed authorize URL string.
        """
        scope_param = "%20".join(scopes)
        return (
            f"{AUTHORIZE_URL}"
            f"?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scope_param}"
            f"&state={state}"
        )

    def exchange(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
    ) -> tuple[str, str] | None:
        """
        @brief Exchange an OAuth authorization code for an access/refresh token pair.

        Posts the authorization_code grant to ``/oauth2/token`` and returns
        ``(access_token, refresh_token)`` on success, or ``None`` when inputs
        are missing or the exchange fails.

        @param code: the authorization code returned in the OAuth redirect.
        @param client_id: Twitch application client id.
        @param client_secret: Twitch application client secret.
        @param redirect_uri: the redirect URI used in the authorize request.
        @return: (access_token, refresh_token) tuple on success, or None on
            failure.
        """
        if not code or not client_id or not client_secret:
            return None
        session = self._session()
        response = session.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=10,
        )
        if response.status_code != 200:
            logger.info("OAuth code exchange failed: %s %s", response.status_code, getattr(response, "text", ""))
            return None
        try:
            data = response.json()
        except Exception:
            logger.exception("OAuth code exchange returned non-JSON body")
            return None
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        if not access or not refresh:
            return None
        return access, refresh

    def start_and_wait(
        self,
        client_id: str,
        scopes: list[str],
        redirect_uri: str = DEFAULT_REDIRECT_URI,
        port: int = DEFAULT_OAUTH_PORT,
        client_secret: str = "",
    ) -> tuple[str, str] | None:
        """
        @brief Run the full interactive OAuth flow and return the token pair.

        Prints the authorize URL for the user to open, then runs a one-shot
        Flask callback server to capture the redirect code. If the server
        fails, falls back to a terminal prompt. The CLIENT_SECRET needed for
        the exchange is taken from the ``client_secret`` argument; only when it
        is empty is the user prompted to paste it after the code arrives.

        @param client_id: Twitch application client id.
        @param scopes: list of OAuth scope strings to request.
        @param redirect_uri: the redirect URI registered for the app.
        @param port: local port for the callback server (default 5003).
        @param client_secret: optional client secret; when non-empty the
            secret prompt is skipped and this value is used for the exchange.
            When empty, the user is prompted to paste the secret at runtime.
        @return: (access_token, refresh_token) tuple on success, or None when
            the flow is cancelled or fails.
        """
        url = self.build_url(client_id, scopes, redirect_uri)
        print(f"Open this URL in your browser and authenticate:\n{url}")
        try:
            return self._run_flask_callback(redirect_uri, client_id, port, client_secret)
        except Exception:
            logger.exception("OAuth callback server failed; falling back to terminal prompt")
            return self._terminal_prompt(client_id, redirect_uri, client_secret)

    def _run_flask_callback(self, redirect_uri: str, client_id: str, port: int, client_secret: str = "") -> tuple[str, str] | None:
        """
        @brief Run a one-shot Flask server to capture the OAuth redirect code.

        Spins up a Werkzeug server on the given port serving ``/oauth/callback``
        in a daemon thread, waits up to 300s for the code, then exchanges the
        captured code for a token pair. The CLIENT_SECRET for the exchange is
        taken from ``client_secret`` when non-empty; otherwise the user is
        prompted to paste it on stdin.

        @param redirect_uri: the redirect URI used in the authorize request.
        @param client_id: Twitch application client id used for the exchange.
        @param port: local port for the callback server.
        @param client_secret: optional client secret; when non-empty no
            secret prompt is shown.
        @return: (access_token, refresh_token) tuple on success, or None when
            no code arrives within the timeout.
        """
        from flask import Flask  # noqa: I001
        from flask import request as flask_request

        app = Flask(__name__)
        holder: dict[str, Any] = {"code": None, "error": None}
        callback_received = threading.Event()

        @app.route("/oauth/callback", methods=["GET"])
        def callback():
            """
            @brief Flask route handler that stores the OAuth code/error from the redirect.

            @return: a simple HTTP response confirming success or describing the
                error from the OAuth provider.
            """
            holder["code"] = flask_request.args.get("code", "")
            holder["error"] = flask_request.args.get("error")
            callback_received.set()
            if holder["code"]:
                return "OK — you can close this tab.", 200
            return f"Error: {holder['error']}", 400

        from werkzeug.serving import make_server

        server = make_server("127.0.0.1", port, app)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        try:
            if not callback_received.wait(timeout=300):
                return None

            code = holder.get("code")
            if not code:
                return None

            secret = client_secret or input("Paste CLIENT_SECRET (for token exchange): ").strip()
            return self.exchange(code, client_id, secret, redirect_uri)
        finally:
            server.server_close()
            thread.join(timeout=5)

    def _terminal_prompt(self, client_id: str, redirect_uri: str, client_secret: str = "") -> tuple[str, str] | None:
        """
        @brief Fall-back flow that asks the user to paste the OAuth code manually.

        Prompts for the authorization code on stdin and exchanges it for a
        token pair. The CLIENT_SECRET is taken from ``client_secret`` when
        non-empty; otherwise the user is prompted to paste it as well. Used
        when the Flask callback server cannot run.

        @param client_id: Twitch application client id used for the exchange.
        @param redirect_uri: the redirect URI used in the authorize request.
        @param client_secret: optional client secret; when non-empty no
            secret prompt is shown.
        @return: (access_token, refresh_token) tuple on success, or None when
            no code is entered.
        """
        code = input("Paste the OAuth code from the redirect URL: ").strip()
        if not code:
            return None
        secret = client_secret or input("Paste CLIENT_SECRET (for token exchange): ").strip()
        return self.exchange(code, client_id, secret, redirect_uri)


__all__ = [
    "BOT_SCOPES",
    "CHANNEL_SCOPES",
    "DEFAULT_OAUTH_PORT",
    "DEFAULT_REDIRECT_URI",
    "OAuthFlowStarter",
]
