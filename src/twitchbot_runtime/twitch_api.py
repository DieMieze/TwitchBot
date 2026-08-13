from __future__ import annotations

import time
from typing import Any

from .logger import get_logger
from .mode import Mode
from .twitch_settings import TwitchSettings

logger = get_logger(__name__)


class TwitchApiClient:
    """Base Helix REST client holding shared credentials + token refresh logic.

    In test/silent modes all sending methods early-return a stub dict and
    perform NO network calls — this is the guarantee that nothing is sent
    outside production.
    """

    # --- Member variables ---
    settings: TwitchSettings  # wrapper around .env Twitch secrets
    mode: Mode  # execution mode (gate for network calls)
    _http: Any  # injectable HTTP session (requests.Session by default)
    _token_refresher: Any  # optional token refresher for 401 retry

    HELIX_BASE = "https://api.twitch.tv/helix"

    def __init__(
        self,
        twitch_settings: TwitchSettings,
        mode: Mode = Mode.PRODUCTION,
        http_session: Any | None = None,
        token_refresher: Any | None = None,
    ) -> None:
        """
        @brief Construct a Helix client bound to settings, mode, and HTTP.

        @param twitch_settings: source of credentials and tokens used for
            Helix requests.
        @param mode: execution mode (``Mode`` or string alias); non-production
            modes disable network calls.
        @param http_session: injectable ``requests``-like session; when
            ``None`` a ``requests.Session`` is lazily created on first use.
        @param token_refresher: optional callback/object able to refresh
            the bot token on a 401 response.
        @return: None
        """
        self.settings = twitch_settings
        self.mode = mode if isinstance(mode, Mode) else Mode.from_string(str(mode))
        self._http = http_session
        self._token_refresher = token_refresher

    @property
    def can_send(self) -> bool:
        """
        @brief Whether the client is allowed to perform real network calls.

        @return: ``True`` only when :attr:`mode` is :attr:`Mode.PRODUCTION`.
        """
        return self.mode is Mode.PRODUCTION

    def _session(self):
        """
        @brief Return a usable HTTP session, lazily creating one if needed.

        Reuses the injected session when provided, otherwise imports
        ``requests`` and creates a new :class:`requests.Session` cached on
        :attr:`_http` for subsequent calls.

        @return: a ``requests``-like session object.
        """
        if self._http is not None:
            return self._http
        import requests

        self._http = requests.Session()
        return self._http

    def _ensure_token(self) -> str:
        """
        @brief Return the current bot OAuth token for Helix authorization.

        @return: the bot OAuth access token from :attr:`settings`.
        """
        return self.settings.bot_oauth_token

    def _helix_headers(self) -> dict[str, str]:
        """
        @brief Build the standard Helix request header set.

        @return: dict with ``Authorization``, ``Client-Id``, and
            ``Content-Type`` headers derived from the bot credentials.
        """
        return {
            "Authorization": f"Bearer {self.settings.bot_oauth_token}",
            "Client-Id": self.settings.bot_client_id,
            "Content-Type": "application/json",
        }

    def _helix(self, method: str, path: str, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> Any:
        """
        @brief Issue a single Helix REST request and return the response.

        @param method: HTTP method (``GET``, ``POST``, ``DELETE``, ...).
        @param path: path under :attr:`HELIX_BASE`, starting with ``/``.
        @param params: optional query parameter mapping.
        @param json: optional JSON body payload.
        @return: the raw response object from the underlying HTTP session.
        """
        session = self._session()
        return session.request(
            method,
            f"{self.HELIX_BASE}{path}",
            params=params,
            json=json,
            headers=self._helix_headers(),
            timeout=10,
        )

    def _stub(self, action: str, **fields: Any) -> dict[str, Any]:
        """
        @brief Build a no-op result dict for non-production modes.

        @param action: name of the action being stubbed out.
        @param fields: extra key/value pairs describing the skipped call.
        @return: a ``{"status": "noop", ...}`` dict echoing the inputs and
            current mode value.
        """
        return {"status": "noop", "action": action, **fields, "mode": self.mode.value}


class ChatSender:
    """Sends a chat message to a channel via ``POST /helix/chat/messages``."""

    # --- Member variables ---
    client: TwitchApiClient  # underlying Helix client used for sending

    def __init__(self, client: TwitchApiClient) -> None:
        """
        @brief Construct a chat sender bound to a Helix client.

        @param client: :class:`TwitchApiClient` used to perform the Helix
            POST and to consult mode/credentials.
        @return: None
        """
        self.client = client

    def send(self, broadcaster_id: str, message: str) -> dict[str, Any]:
        """
        @brief Send a chat message to a channel as the bot user.

        In non-production modes returns a no-op stub without any network
        call. Rejects empty broadcaster ids with an error result.

        @param broadcaster_id: numeric Twitch user id of the target channel.
        @param message: chat message text to send.
        @return: ``{"status": "sent"|"noop"|"error", ...}`` describing the
            outcome and (on success) the Helix response payload.
        """
        if not self.client.can_send:
            logger.info("ChatSender noop (%s mode): broadcaster_id=%s", self.client.mode.value, broadcaster_id)
            return self.client._stub("send_chat", broadcaster_id=broadcaster_id, message=message)
        if not broadcaster_id:
            logger.warning("ChatSender.send called with empty broadcaster_id")
            return {"status": "error", "error": "missing_broadcaster_id"}
        response = self.client._helix(
            "POST",
            "/chat/messages",
            json={
                "broadcaster_id": broadcaster_id,
                "sender_id": self.client.settings.bot_channel_id,
                "message": message,
            },
        )
        if response.status_code in (200, 202):
            data = response.json()
            return {"status": "sent", "response": data}
        logger.warning("Chat send failed: %s %s", response.status_code, getattr(response, "text", ""))
        return {"status": "error", "status_code": response.status_code, "body": getattr(response, "text", "")}


class ModerationActor:
    """Performs ban/timeout/unban/delete/purge via Helix moderation endpoints.

    ``target`` may be a login string or numeric user id; logins are resolved
    to numeric ids via ``GET /helix/users?login=`` with an in-memory cache.
    """

    # --- Member variables ---
    client: TwitchApiClient  # underlying Helix client used for moderation
    _user_id_cache: dict[str, str]  # login -> numeric user id lookup cache

    def __init__(self, client: TwitchApiClient) -> None:
        """
        @brief Construct a moderation actor bound to a Helix client.

        @param client: :class:`TwitchApiClient` used for Helix calls and to
            consult mode/credentials.
        @return: None
        """
        self.client = client
        self._user_id_cache: dict[str, str] = {}

    def _resolve_user_id(self, target: str) -> str:
        """
        @brief Resolve a login or numeric id to a numeric user id.

        Numeric targets are returned unchanged. Login strings are looked up
        via ``GET /helix/users?login=`` and cached case-insensitively.

        @param target: numeric user id or login name to resolve.
        @return: the numeric user id, or ``""`` when it cannot be resolved.
        """
        if not target:
            return ""
        if target.isdigit():
            return target
        cached = self._user_id_cache.get(target.lower())
        if cached:
            return cached
        response = self.client._helix("GET", "/users", params={"login": target})
        if response.status_code == 200:
            users = response.json().get("data", [])
            if users:
                user_id = users[0].get("id", "")
                if user_id:
                    self._user_id_cache[target.lower()] = user_id
                    return user_id
        logger.warning("ModerationActor could not resolve user id for %s", target)
        return ""

    def _moderation_payload(self, user_id: str, reason: str | None, duration: int | None = None) -> dict[str, Any]:
        """
        @brief Build the ``data`` payload for a ban/timeout request.

        @param user_id: numeric target user id.
        @param reason: optional ban reason text.
        @param duration: optional timeout duration in seconds; omitted when
            ``None`` or non-positive.
        @return: dict suitable as the ``data`` field of a ban POST body.
        """
        data: dict[str, Any] = {"user_id": user_id}
        if reason:
            data["reason"] = reason
        if duration is not None and duration > 0:
            data["duration"] = duration
        return data

    def _ban_endpoint(self, action: str, target: str, reason: str | None = None, duration: int | None = None) -> dict[str, Any]:
        """
        @brief Shared implementation for ban and timeout actions.

        Resolves the target to a user id, posts to the ban endpoint with the
        broadcaster/moderator ids from settings, and reports the outcome.

        @param action: label describing the action (e.g. ``"ban"``,
            ``"timeout"``).
        @param target: numeric user id or login name to moderate.
        @param reason: optional ban reason text.
        @param duration: optional timeout duration in seconds.
        @return: ``{"status": "noop"|"executed"|"error", ...}`` result dict.
        """
        if not self.client.can_send:
            return self.client._stub(action, target=target, reason=reason, duration=duration)
        if not target:
            logger.warning("ModerationActor.%s called with empty target", action)
            return {"status": "error", "error": "missing_target"}
        user_id = self._resolve_user_id(target)
        if not user_id:
            return {"status": "error", "error": "unresolved_target", "target": target}
        response = self.client._helix(
            "POST",
            "/moderation/bans",
            params={
                "broadcaster_id": self.client.settings.twitch_channel_id,
                "moderator_id": self.client.settings.bot_channel_id,
            },
            json={"data": self._moderation_payload(user_id, reason, duration)},
        )
        if response.status_code in (200, 204):
            return {"status": "executed", "action": action, "target": target, "user_id": user_id}
        logger.warning("Moderation ban failed: %s %s", response.status_code, getattr(response, "text", ""))
        return {"status": "error", "status_code": response.status_code, "body": getattr(response, "text", "")}

    def ban(self, target: str, reason: str | None = None) -> dict[str, Any]:
        """
        @brief Permanently ban a user from the channel.

        @param target: numeric user id or login name to ban.
        @param reason: optional ban reason text.
        @return: result dict from :meth:`_ban_endpoint`.
        """
        return self._ban_endpoint("ban", target, reason=reason)

    def timeout(self, target: str, duration: int, reason: str | None = None) -> dict[str, Any]:
        """
        @brief Temporarily timeout a user for a given duration.

        @param target: numeric user id or login name to timeout.
        @param duration: timeout length in seconds.
        @param reason: optional timeout reason text.
        @return: result dict from :meth:`_ban_endpoint`.
        """
        return self._ban_endpoint("timeout", target, reason=reason, duration=duration)

    def unban(self, target: str) -> dict[str, Any]:
        """
        @brief Revoke a ban for a user via ``DELETE /moderation/bans``.

        @param target: numeric user id or login name to unban.
        @return: ``{"status": "noop"|"executed"|"error", ...}`` result dict.
        """
        if not self.client.can_send:
            return self.client._stub("unban", target=target)
        user_id = self._resolve_user_id(target)
        if not user_id:
            return {"status": "error", "error": "unresolved_target", "target": target}
        response = self.client._helix(
            "DELETE",
            "/moderation/bans",
            params={
                "broadcaster_id": self.client.settings.twitch_channel_id,
                "moderator_id": self.client.settings.bot_channel_id,
                "user_id": user_id,
            },
        )
        if response.status_code in (200, 204):
            return {"status": "executed", "action": "unban", "target": target}
        return {"status": "error", "status_code": response.status_code}

    def delete_message(self, message_id: str) -> dict[str, Any]:
        """
        @brief Delete a single chat message via ``DELETE /moderation/chat``.

        @param message_id: Twitch message id to remove.
        @return: ``{"status": "noop"|"executed"|"error", ...}`` result dict.
        """
        if not self.client.can_send:
            return self.client._stub("delete_message", message_id=message_id)
        if not message_id:
            return {"status": "error", "error": "missing_message_id"}
        response = self.client._helix(
            "DELETE",
            "/moderation/chat",
            params={
                "broadcaster_id": self.client.settings.twitch_channel_id,
                "moderator_id": self.client.settings.bot_channel_id,
                "message_id": message_id,
            },
        )
        if response.status_code in (200, 204):
            return {"status": "executed", "action": "delete_message", "message_id": message_id}
        return {"status": "error", "status_code": response.status_code}

    def purge(self, target: str) -> dict[str, Any]:
        """
        @brief Placeholder purge action (currently a no-op stub).

        Full purge requires resolving a user's recent message id, which is
        out of scope for the current Helix implementation.

        @param target: numeric user id or login name whose messages would be
            purged.
        @return: a ``{"status": "noop", ...}`` dict noting the limitation.
        """
        if not self.client.can_send:
            return self.client._stub("purge", target=target)
        logger.info("purge target=%s (lookup message_id is out-of-scope; noop stub)", target)
        return {"status": "noop", "action": "purge", "target": target, "reason": "lookup_message_id_unsupported"}


class ClipCreator:
    """Creates a Twitch clip via ``POST /helix/clips`` for the configured
    streamer (``TWITCH_CHANNEL_ID``)."""

    # --- Member variables ---
    client: TwitchApiClient  # underlying Helix client used to create clips

    def __init__(self, client: TwitchApiClient) -> None:
        """
        @brief Construct a clip creator bound to a Helix client.

        @param client: :class:`TwitchApiClient` used for the Helix POST and
            to read the configured broadcaster id.
        @return: None
        """
        self.client = client

    def create(self, title: str | None = None, duration: int = 30) -> str:
        """
        @brief Create a clip for the configured broadcaster and return a URL.

        In non-production modes returns an empty string without any network
        call. On success returns the clip's ``edit_url`` or a
        ``clips.twitch.tv`` URL built from the clip id.

        @param title: optional clip title; when provided the clip is created
            with a broadcast delay (``has_delay=true``).
        @param duration: desired clip duration in seconds (server-enforced).
        @return: the clip's edit/view URL, or ``""`` on failure/no-op.
        """
        if not self.client.can_send:
            logger.info("ClipCreator noop (%s mode)", self.client.mode.value)
            return ""
        broadcaster_id = self.client.settings.twitch_channel_id
        if not broadcaster_id:
            logger.error("ClipCreator.create: TWITCH_CHANNEL_ID is empty")
            return ""
        params: dict[str, Any] = {"broadcaster_id": broadcaster_id}
        if title:
            params["has_delay"] = "true"
        response = self.client._helix("POST", "/clips", params=params)
        if response.status_code in (200, 202):
            data = response.json()
            clips = data.get("data", []) if isinstance(data, dict) else []
            if clips:
                clip_id = clips[0].get("id", "")
                edit_url = clips[0].get("edit_url", "")
                return edit_url or f"https://clips.twitch.tv/{clip_id}"
        logger.warning("Clip creation failed: %s %s", response.status_code, getattr(response, "text", ""))
        return ""


__all__ = [
    "ChannelInfoFetcher",
    "ChatSender",
    "ClipCreator",
    "ModerationActor",
    "TwitchApiClient",
]


class ChannelInfoFetcher:
    """Fetches the broadcaster's current stream category (game_name) via
    ``GET /helix/channels``, cached per broadcaster id with a TTL.

    Used by counter reactions with ``category_dependent: true`` to key
    counters per game. Non-production modes return ``""`` without any network
    call (mirroring :class:`ClipCreator`)."""

    # --- Member variables ---
    client: TwitchApiClient  # underlying Helix client used for channel info
    _cache: dict[str, tuple[float, str]]  # broadcaster_id -> (timestamp, game_name)
    cache_ttl: float  # cache entry lifetime in seconds

    def __init__(self, client: TwitchApiClient, cache_ttl: float = 60.0) -> None:
        """
        @brief Construct a channel-info fetcher bound to a Helix client.

        @param client: :class:`TwitchApiClient` used for the Helix GET and to
            consult mode/credentials.
        @param cache_ttl: lifetime of a cached ``game_name`` entry in seconds.
            Subsequent calls within the TTL return the cached value without a
            network request.
        @return: None
        """
        self.client = client
        self._cache: dict[str, tuple[float, str]] = {}
        self.cache_ttl = cache_ttl

    def game_name(self) -> str:
        """
        @brief Return the broadcaster's current stream ``game_name``.

        In non-production modes returns an empty string without any network
        call. On success returns the cached (or freshly fetched) ``game_name``.
        On error/empty data returns ``""``.

        @return: the broadcaster's current ``game_name``, or ``""`` when
            unavailable (non-production, missing id, or a Helix error).
        """
        if not self.client.can_send:
            logger.info("ChannelInfoFetcher noop (%s mode)", self.client.mode.value)
            return ""
        broadcaster_id = self.client.settings.twitch_channel_id
        if not broadcaster_id:
            logger.error("ChannelInfoFetcher.game_name: TWITCH_CHANNEL_ID is empty")
            return ""
        now = time.time()
        cached = self._cache.get(broadcaster_id)
        if cached is not None and (now - cached[0]) < self.cache_ttl:
            return cached[1]
        try:
            response = self.client._helix("GET", "/channels", params={"broadcaster_id": broadcaster_id})
        except Exception:
            logger.exception("ChannelInfoFetcher GET /channels failed")
            return ""
        if response.status_code != 200:
            logger.warning("ChannelInfoFetcher failed: %s %s", response.status_code, getattr(response, "text", ""))
            return ""
        try:
            data = response.json()
        except ValueError:
            return ""
        items = data.get("data", []) if isinstance(data, dict) else []
        game = items[0].get("game_name", "") if items else ""
        game = game or ""
        self._cache[broadcaster_id] = (now, game)
        return game
