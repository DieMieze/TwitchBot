from __future__ import annotations

from typing import Any

from ..expression.evaluator import walk_trigger_leaves
from ..logger import get_logger

logger = get_logger(__name__)


EVENT_TYPES_FOR_TRIGGERS = {
    "command": "channel.chat.message",
    "channel_point_reward": "channel.channel_points_custom_reward_redemption.add",
    "first_time_chatter": "channel.chat.message",
    "new_chatter": "channel.chat.message",
    "follow": "channel.follow",
    "sub": "channel.subscribe",
    "cheer": "channel.cheer",
    "raid": "channel.raid",
}

DEFAULT_SUBSCRIPTION_TYPES = [
    "channel.chat.message",
    "channel.channel_points_custom_reward_redemption.add",
    "channel.follow",
    "channel.subscribe",
    "channel.cheer",
    "channel.raid",
]


class EventSubClient:
    """Registers and tears down Twitch EventSub webhook subscriptions.

    Accepts either a ``TwitchSettings`` wrapper (preferred) or a plain dict
    for backward compatibility. All HTTP calls go through the injected
    ``http_session`` (a ``requests.Session`` by default) so tests can inject
    a fake transport without touching the network. App access tokens are
    obtained via an injectable ``AppTokenFetcher`` (also falls back to the
    legacy ``fetch_app_access_token`` method).
    """

    HELIX_BASE = "https://api.twitch.tv/helix/event_sub/subscriptions"

    # --- Member variables ---
    client_id: str  # Twitch app client id used for Helix auth
    client_secret: str  # Twitch app client secret used for token requests
    webhook_secret: str  # EventSub webhook signing secret
    broadcaster_user_id: str  # numeric Twitch id of the channel being subscribed to
    bot_user_id: str  # numeric Twitch id of the bot user (moderator)
    _twitch_settings: Any  # original TwitchSettings wrapper when built from one, else None
    _http: Any  # injectable requests.Session transport (None = lazy create)
    _app_token_fetcher: Any  # injectable AppTokenFetcher (None = legacy HTTP fetch)
    _app_access_token: str | None  # cached app access token, None until fetched
    _subscription_ids: list[str]  # ids of currently registered EventSub subscriptions

    def __init__(
        self,
        twitch_settings: Any,
        http_session: Any | None = None,
        app_token_fetcher: Any | None = None,
    ) -> None:
        """
        @brief Construct an EventSubClient from settings or a dict.

        Initializes the client credentials and ids from either a
        TwitchSettings wrapper or a plain dict, and stores the optional
        HTTP session and app token fetcher for dependency injection.

        @param twitch_settings: TwitchSettings wrapper (has bot_client_id,
            bot_client_secret, twitch_channel_id, bot_channel_id) or a plain
            dict with client_id/client_secret/webhook_secret/callback_url/
            broadcaster_user_id/bot_user_id.
        @param http_session: optional requests.Session-like transport; when
            None a real session is created lazily on first HTTP call.
        @param app_token_fetcher: optional AppTokenFetcher-like object; when
            None the legacy HTTP client_credentials flow is used.
        @return: None
        """
        if hasattr(twitch_settings, "bot_client_id"):
            self._from_twitch_settings(twitch_settings)
        else:
            self._from_dict(twitch_settings or {})
        self._http = http_session
        self._app_token_fetcher = app_token_fetcher
        self._app_access_token: str | None = None
        self._subscription_ids: list[str] = []

    def _from_twitch_settings(self, settings: Any) -> None:
        """
        @brief Populate members from a TwitchSettings wrapper.

        Copies bot client id/secret, broadcaster and bot user ids from the
        wrapper and stores it for later use; webhook_secret is left empty
        (read from settings.json elsewhere).

        @param settings: TwitchSettings-like object exposing
            bot_client_id, bot_client_secret, twitch_channel_id,
            bot_channel_id.
        @return: None
        """
        self.client_id = settings.bot_client_id
        self.client_secret = settings.bot_client_secret
        self.webhook_secret = ""
        self.broadcaster_user_id = settings.twitch_channel_id
        self.bot_user_id = settings.bot_channel_id
        self._twitch_settings = settings

    def _from_dict(self, settings: dict[str, Any]) -> None:
        """
        @brief Populate members from a plain settings dict (legacy path).

        Reads client_id, client_secret, webhook_secret, callback_url,
        broadcaster_user_id and bot_user_id (falling back to
        broadcaster_user_id) from the dict, and clears _twitch_settings.

        @param settings: dict with optional keys client_id, client_secret,
            webhook_secret, callback_url, broadcaster_user_id, bot_user_id.
        @return: None
        """
        self.client_id = settings.get("client_id", "")
        self.client_secret = settings.get("client_secret", "")
        self.webhook_secret = settings.get("webhook_secret", "")
        self.callback_url = settings.get("callback_url", "")
        self.broadcaster_user_id = settings.get("broadcaster_user_id", "")
        self.bot_user_id = settings.get("bot_user_id", settings.get("broadcaster_user_id", ""))
        self._twitch_settings = None

    def set_callback_url(self, callback_url: str) -> None:
        """
        @brief Set the EventSub webhook callback URL.

        Stores the public tunnel URL that Twitch will POST events to, set
        after the cloudflared tunnel is started at runtime.

        @param callback_url: fully qualified public callback URL
            (e.g. https://<tunnel>.trycloudflare.com/eventsub).
        @return: None
        """
        self.callback_url = callback_url

    def _session(self):
        """
        @brief Return the HTTP session, creating a real one lazily.

        Returns the injected session when present; otherwise imports
        requests and creates a new Session cached on _http for reuse.

        @return: a requests.Session-like transport object.
        """
        if self._http is not None:
            return self._http
        import requests

        self._http = requests.Session()
        return self._http

    def subscription_types_for_triggers(self, triggers: list[dict[str, Any]]) -> list[str]:
        """
        @brief Derive the EventSub subscription types needed for triggers.

        Walks each trigger's ``when`` tree via :func:`walk_trigger_leaves`,
        maps each event-leaf condition type to an EventSub subscription type
        (``compare`` leaves contribute no EventSub type), then appends any
        DEFAULT_SUBSCRIPTION_TYPES not already included, returning a
        de-duplicated ordered list.

        @param triggers: list of runtime trigger dicts (each with a ``when``
            trigger tree).
        @return: ordered, de-duplicated list of EventSub subscription type
            strings to register.
        """
        types: list[str] = []
        seen: set[str] = set()

        for trigger in triggers or []:
            if not isinstance(trigger, dict):
                continue
            when_node = trigger.get("when")
            if when_node is None:
                continue
            for condition in walk_trigger_leaves(when_node):
                cond_type = condition.get("type")
                mapped = EVENT_TYPES_FOR_TRIGGERS.get(cond_type or "")
                if mapped and mapped not in seen:
                    seen.add(mapped)
                    types.append(mapped)

        for default_type in DEFAULT_SUBSCRIPTION_TYPES:
            if default_type not in seen:
                seen.add(default_type)
                types.append(default_type)

        return types

    def fetch_app_access_token(self) -> str:
        """
        @brief Obtain and cache a Twitch app access token.

        Returns the cached token when present; otherwise uses the injected
        AppTokenFetcher when available, falling back to the legacy
        client_credentials HTTP flow against id.twitch.tv. The fetched token
        is cached on _app_access_token.

        @return: the app access token string.
        """
        if self._app_access_token:
            return self._app_access_token
        if self._app_token_fetcher is not None:
            token = self._app_token_fetcher.fetch(self.client_id, self.client_secret)
            self._app_access_token = token
            return token

        session = self._session()
        response = session.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        response.raise_for_status()
        self._app_access_token = response.json().get("access_token", "")
        if not self._app_access_token:
            raise RuntimeError("Twitch did not return an app access token")
        return self._app_access_token

    def register_subscriptions(self, subscription_types: list[str]) -> list[str]:
        """
        @brief Register EventSub webhook subscriptions via Helix.

        Fetches an app access token, then POSTs each subscription type to
        the Helix event_sub endpoint with the appropriate condition,
        version, and webhook transport. Successful ids (HTTP 202) are
        appended to _subscription_ids; failures are logged but do not abort.

        @param subscription_types: list of EventSub subscription type
            strings to register.
        @return: a copy of the list of successfully registered subscription
            ids.
        """
        token = self.fetch_app_access_token()
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        for subscription_type in subscription_types:
            condition = self._condition_for(subscription_type)
            payload = {
                "type": subscription_type,
                "version": self._version_for(subscription_type),
                "condition": condition,
                "transport": {
                    "method": "webhook",
                    "callback": self.callback_url,
                    "secret": self.webhook_secret,
                },
            }
            try:
                response = self._session().post(
                    self.HELIX_BASE,
                    headers=headers,
                    json=payload,
                    timeout=10,
                )
                if response.status_code in (202,):
                    data = response.json()
                    sub_id = data.get("data", [{}])[0].get("id")
                    if sub_id:
                        self._subscription_ids.append(sub_id)
                    logger.info("Registered EventSub subscription %s", subscription_type)
                else:
                    logger.warning(
                        "EventSub subscription %s failed: %s %s",
                        subscription_type,
                        response.status_code,
                        response.text,
                    )
            except Exception:
                logger.exception("Failed to register EventSub subscription %s", subscription_type)

        return list(self._subscription_ids)

    def _version_for(self, subscription_type: str) -> str:
        """
        @brief Return the EventSub API version for a subscription type.

        Returns "2" for channel.follow (which requires v2) and "1" for all
        other subscription types.

        @param subscription_type: EventSub subscription type string.
        @return: the API version string ("1" or "2").
        """
        if subscription_type == "channel.follow":
            return "2"
        return "1"

    def _condition_for(self, subscription_type: str) -> dict[str, Any]:
        """
        @brief Build the EventSub condition object for a subscription type.

        Returns the broadcaster/moderator/reward ids required by each
        subscription type. Chat and follow subscriptions use the bot user
        id as user_id/moderator_user_id; raids use to_broadcaster_user_id;
        others default to broadcaster_user_id only.

        @param subscription_type: EventSub subscription type string.
        @return: condition dict to send in the subscription payload.
        """
        if subscription_type == "channel.chat.message":
            return {
                "broadcaster_user_id": self.broadcaster_user_id,
                "user_id": self.bot_user_id,
            }
        if subscription_type == "channel.follow":
            return {
                "broadcaster_user_id": self.broadcaster_user_id,
                "moderator_user_id": self.bot_user_id,
            }
        if subscription_type.startswith("channel.channel_points_custom_reward_redemption"):
            return {
                "broadcaster_user_id": self.broadcaster_user_id,
            }
        if subscription_type == "channel.raid":
            return {"to_broadcaster_user_id": self.broadcaster_user_id}
        return {"broadcaster_user_id": self.broadcaster_user_id}

    def delete_subscriptions(self) -> None:
        """
        @brief Delete all currently registered EventSub subscriptions.

        Fetches an app access token and DELETEs each tracked subscription
        id via Helix; per-id failures are logged but do not stop the loop.
        Clears _subscription_ids afterwards.

        @return: None
        """
        token = self.fetch_app_access_token()
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
        }
        for sub_id in list(self._subscription_ids):
            try:
                self._session().delete(
                    f"{self.HELIX_BASE}?id={sub_id}",
                    headers=headers,
                    timeout=10,
                )
            except Exception:
                logger.exception("Failed to delete EventSub subscription %s", sub_id)
        self._subscription_ids.clear()

    @property
    def subscription_ids(self) -> list[str]:
        """
        @brief Read-only copy of the registered subscription ids.

        @return: a new list containing the currently tracked EventSub
            subscription id strings.
        """
        return list(self._subscription_ids)
