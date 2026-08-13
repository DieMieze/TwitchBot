from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .chatter_tracker import ChatterTracker
from .counter_handler import CounterHandler
from .feature_manager import FeatureManager
from .features import (
    ModerationFeature,
    OverlayFeature,
    WebUIFeature,
)
from .logger import get_logger
from .mode import Mode
from .moderation_handler import ModerationHandler
from .overlay import OverlayManager
from .ports import resolve_port_or_exit
from .reaction_engine import ReactionEngine
from .settings import load_settings
from .silent_collector import SilentEventCollector
from .trigger_resolver import TriggerResolver
from .tunnel import TunnelManager

logger = get_logger(__name__)


def _is_interactive() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        return False


class TwitchBot:
    """Modular Twitch bot runtime that composes features and executes reactions."""

    # --- Member variables ---
    settings: dict[str, Any]  # loaded settings.json content
    handlers: dict[str, Callable[..., Any]]  # injected side-effect handler overrides
    mode: Mode  # execution mode (test/silent/production)
    overlay_manager: OverlayManager  # overlay action facade
    feature_manager: FeatureManager  # feature registry (moderation/overlay/streampet/webui)
    trigger_resolver: TriggerResolver  # matches triggers against events
    silent_collector: Any  # SilentEventCollector (silent mode) or None
    reaction_engine: ReactionEngine  # dispatches reactions to handlers
    _sent: list[Any]  # in-memory record of sent side-effects (test/silent)
    _running: bool  # whether the blocking run loop is active
    _timer_scheduler: Any  # TimerScheduler driving time triggers
    _webhook_server: Any  # EventSub webhook Flask server handle
    _eventsub_client: Any  # EventSubClient managing subscriptions
    _tunnel_manager: Any  # cloudflared TunnelManager handle (production only)
    _twitch_api_client: Any  # TwitchApiClient for Helix sending (production only)
    _twitch_settings_obj: Any  # TwitchSettings .env wrapper (production only)
    _moderation_actor: Any  # ModerationActor for real ban/timeout (production only)
    _channel_info_fetcher: Any  # ChannelInfoFetcher for stream category (production only)
    _app_access_token: str  # cached app access token (production startup)
    _app_token_fetcher: Any  # AppTokenFetcher instance used at startup
    _counter_handler: CounterHandler  # persistent counter handler (injected into resolver + engine)
    _chatter_tracker: ChatterTracker  # in-memory last-seen map for new_chatter (inactivity-window) triggers

    def __init__(
        self,
        settings_path: str | Path | None = None,
        handlers: dict[str, Callable[..., Any]] | None = None,
        execution_mode: str | None = None,
    ) -> None:
        """
        @brief Construct the TwitchBot runtime and wire up its components.

        Loads settings, resolves the execution mode, builds the overlay/feature
        managers and trigger resolver, then assembles the ReactionEngine with
        mode-appropriate side-effect handlers. Production mode also initializes
        the Twitch API client and moderation actor.

        @param settings_path: optional path to settings.json; None uses the
            default loader resolution.
        @param handlers: optional dict of side-effect handler overrides
            (send_chat/create_clip/moderation_handler/overlay_dispatch/
            counter_handler/streampet_handler); missing keys fall back to
            mode-aware defaults.
        @param execution_mode: optional mode override ("test"/"silent"/
            "production"); None reads runtime.execution_mode from settings
            (defaulting to "test").
        @return: None
        """
        self.settings = load_settings(settings_path)
        self.handlers = handlers or {}
        self._settings_path = str(settings_path) if settings_path is not None else "settings.json"

        mode_str = execution_mode or self.settings.get("runtime", {}).get("execution_mode", "test")
        self.mode = Mode.from_string(mode_str)

        runtime_settings = self.settings.get("runtime", {})
        feature_settings = self.settings.get("features", {})

        overlay_enabled = bool(feature_settings.get("overlay", {}).get("enabled", False))
        real_backend = overlay_enabled and self.mode in (Mode.PRODUCTION, Mode.TEST)
        store_path = runtime_settings.get("overlay_actions_path", "output/overlay_actions.jsonl")
        overlay_port: int | None = None
        if real_backend:
            overlay_port = resolve_port_or_exit(
                "overlay",
                self.settings,
                self._settings_path,
                interactive=_is_interactive(),
            )
        self.overlay_manager = OverlayManager(
            real_backend=real_backend,
            store_path=store_path,
            overlay_port=overlay_port,
        )
        self.feature_manager = FeatureManager()
        self._counter_handler = CounterHandler()
        self._chatter_tracker = ChatterTracker()
        self.trigger_resolver = TriggerResolver(
            self.settings.get("triggers", []),
            counter_handler=self._counter_handler,
            chatter_tracker=self._chatter_tracker,
        )

        self._sent: list[Any] = []
        self._running: bool = False
        self._timer_scheduler: Any = None
        self._webhook_server: Any = None
        self._webhook_port: int | None = None
        self._eventsub_client: Any = None
        self._tunnel_manager: Any = None
        self._twitch_api_client: Any = None
        self._twitch_settings_obj: Any = None
        self._moderation_actor: Any = None
        self._channel_info_fetcher: Any = None

        if self.mode is Mode.SILENT:
            silent_store = runtime_settings.get("silent_events_path", "output/silent_events.jsonl")
            self.silent_collector = SilentEventCollector(
                store_path=silent_store,
                max_per_type=runtime_settings.get("silent_max_per_type", 50),
            )
        else:
            self.silent_collector = None

        if self.mode is Mode.PRODUCTION:
            self._setup_twitch_api()

        self.reaction_engine = ReactionEngine(
            send_chat=self._make_send_chat(),
            overlay_dispatch=self.handlers.get("overlay_dispatch", self.overlay_manager.dispatch),
            create_clip=self._make_create_clip(),
            counter_handler=self._make_counter_handler(),
            moderation_handler=self._make_moderation_handler(),
            streampet_handler=self.handlers.get("streampet_handler", self._noop_streampet),
            speech_bubble_provider=self._make_speech_bubble_provider(),
            chatter_tracker=self._chatter_tracker,
            stream_category_provider=self._make_stream_category_provider(),
        )

        self._register_features()

    def _setup_twitch_api(self) -> None:
        """
        @brief Initialize the TwitchApiClient and ModerationActor for production.

        Loads TwitchSettings from .env and, when credentials are complete,
        constructs a TwitchApiClient (mode-gated to production) plus a
        ModerationActor wrapping it. Skips silently when send_chat and
        create_clip handlers are already injected, and logs a warning when
        the .env is incomplete so production sending degrades to no-op.

        @return: None
        """
        if self.handlers.get("send_chat") is not None and self.handlers.get("create_clip") is not None:
            return
        try:
            from .twitch_api import ChannelInfoFetcher, ModerationActor, TwitchApiClient
            from .twitch_settings import TwitchSettings

            self._twitch_settings_obj = TwitchSettings.load()
            if not self._twitch_settings_obj.is_complete():
                logger.warning(
                    "Twitch credentials incomplete (.env missing keys: %s); "
                    "production sending will be no-op. Run scripts/get_all_scopes.py.",
                    ", ".join(self._twitch_settings_obj.missing_bot_keys()),
                )
                return
            self._twitch_api_client = TwitchApiClient(self._twitch_settings_obj, mode=self.mode)
            self._moderation_actor = ModerationActor(self._twitch_api_client)
            self._channel_info_fetcher = ChannelInfoFetcher(self._twitch_api_client)
        except Exception:
            logger.exception("Failed to set up TwitchApiClient; production sending stays stubbed")

    def _make_counter_handler(self):
        """Build the counter-handler callable for the ReactionEngine.

        Honors an injected override first. Otherwise returns an adapter
        wrapping :meth:`CounterHandler.handle` that also exposes
        ``resolve_placeholders`` so the engine can resolve ``{counter:...}``
        placeholders in chat_reply/overlay messages (the engine looks the
        attribute up on the injected callable).
        """
        injected = self.handlers.get("counter_handler")
        if injected is not None:
            return injected

        def _adapter(action: str, payload: dict[str, Any]) -> dict[str, Any]:
            return self._counter_handler.handle(action, payload)

        _adapter.resolve_placeholders = self._counter_handler.resolve_placeholders
        return _adapter

    def _make_moderation_handler(self):
        """
        @brief Build the ModerationHandler instance for the ReactionEngine.

        Returns an injected override when present; otherwise constructs a
        ModerationHandler bound to the production ModerationActor (or None in
        test/silent mode, where moderation stays a stub).

        @return: a ModerationHandler (injected or freshly constructed).
        """
        injected = self.handlers.get("moderation_handler")
        if injected is not None:
            return injected
        actor = self._moderation_actor if self.mode is Mode.PRODUCTION else None
        return ModerationHandler(mode=self.mode, actor=actor)

    def _make_send_chat(self) -> Callable[..., Any]:
        """
        @brief Build the send_chat callable used by the ReactionEngine.

        Honors an injected override first; in test/silent mode returns a lambda
        that records the call into self._sent; when a TwitchApiClient is
        available returns a bound ChatSender.send; otherwise falls back to the
        self._send_chat stub.

        @return: a callable(broadcaster_id, message) performing chat sending.
        """
        injected = self.handlers.get("send_chat")
        if injected is not None:
            return injected
        if self.mode in (Mode.TEST, Mode.SILENT):
            return lambda broadcaster_id, message: self._sent.append(("chat", broadcaster_id, message))
        if self._twitch_api_client is not None:
            from .twitch_api import ChatSender

            return ChatSender(self._twitch_api_client).send
        return self._send_chat

    def _make_create_clip(self) -> Callable[..., Any]:
        """
        @brief Build the create_clip callable used by the ReactionEngine.

        Honors an injected override first; in test/silent mode returns a lambda
        recording the call into self._sent; when a TwitchApiClient is
        available returns a bound ClipCreator.create; otherwise falls back to
        the self._create_clip stub.

        @return: a callable() that creates a clip and returns its id/url.
        """
        injected = self.handlers.get("create_clip")
        if injected is not None:
            return injected
        if self.mode in (Mode.TEST, Mode.SILENT):

            def _clip_stub() -> str:
                self._sent.append(("clip",))
                return ""

            return _clip_stub
        if self._twitch_api_client is not None:
            from .twitch_api import ClipCreator

            return ClipCreator(self._twitch_api_client).create
        return self._create_clip

    def _make_speech_bubble_provider(self) -> Callable[[], dict[str, Any] | None]:
        """
        @brief Build the speech-bubble config provider for the ReactionEngine.

        Honors an injected override first (``speech_bubble_provider``). Otherwise
        returns a callable that reads ``speech_bubble_text``/``speech_bubble_toggle``
        fresh from ``Stream_Pet.json`` on each call (same file the overlay subprocess
        reads via ``facade._load_config``; parent-side path mirrors that pattern).
        Fresh-per-call avoids cache-coherence issues with concurrent Pos-UI/Config-UI
        writes (the file is small). Missing or unreadable file yields None, which
        the engine treats as "no speech bubble".

        @return: a callable() returning the raw speech-bubble config dict or None.
        """
        injected = self.handlers.get("speech_bubble_provider")
        if injected is not None:
            return injected

        config_path = Path(__file__).resolve().parents[2] / "Stream_Pet.json"

        def _provider() -> dict[str, Any] | None:
            try:
                with open(config_path, encoding="utf-8") as handle:
                    data = json.load(handle)
                return data if isinstance(data, dict) else None
            except (OSError, ValueError):
                return None

        return _provider

    def _make_stream_category_provider(self) -> Callable[[], str]:
        """
        @brief Build the stream-category provider for the ReactionEngine.

        Honors an injected override first (``stream_category_provider``).
        Otherwise, in production returns a callable bound to the
        :class:`ChannelInfoFetcher` (cached ``GET /channels`` game_name). In
        test/silent mode returns a stub yielding ``""`` (the counter falls
        back to the ``"default"`` category).

        @return: a callable() returning the broadcaster's current
            ``game_name`` (or ``""`` when unavailable).
        """
        injected = self.handlers.get("stream_category_provider")
        if injected is not None:
            return injected
        if self.mode is Mode.PRODUCTION and self._channel_info_fetcher is not None:
            return lambda: self._channel_info_fetcher.game_name()
        return lambda: ""

    def _register_features(self) -> None:
        """
        @brief Register all built-in features with the FeatureManager.

        Reads the "features" section of settings and registers Moderation,
        Overlay and WebUI features with their respective enabled flags
        (defaulting each to a safe value when unspecified). StreamPet is no
        longer a feature: it is produced by configured triggers whose
        reactions include a ``streampet`` entry, executed by the
        ReactionEngine and mirrored to the overlay.

        @return: None
        """
        feature_settings = self.settings.get("features", {})

        self.feature_manager.register(
            ModerationFeature(enabled=feature_settings.get("moderation", {}).get("enabled", True))
        )
        self.feature_manager.register(
            OverlayFeature(enabled=feature_settings.get("overlay", {}).get("enabled", False))
        )
        self.feature_manager.register(
            WebUIFeature(enabled=feature_settings.get("webui", {}).get("enabled", True))
        )

    def start(self) -> dict[str, Any]:
        """
        @brief Start background services (overlay backend, scheduler, webhook, EventSub).

        Does NOT block. The webhook server is started in a background thread so
        Twitch can verify the callback before subscriptions are registered. Use
        :meth:`run` for the blocking entry point.

        @return: dict with "status" ("started") and "mode" (current mode value).
        """
        if self.overlay_manager.backend is not None:
            backend_start = getattr(self.overlay_manager.backend, "start", None)
            if callable(backend_start):
                backend_start()

        if self.mode in {Mode.SILENT, Mode.PRODUCTION}:
            self._run_startup_checks()
            self._start_scheduler()
            self._start_webhook(block=False)
            self._start_eventsub()

        return {"status": "started", "mode": self.mode.value}

    def stop(self) -> dict[str, Any]:
        """
        @brief Stop background services started by :meth:`start` / :meth:`run`.

        Tears down EventSub subscriptions, the cloudflared tunnel, the timer
        scheduler and the overlay backend (best-effort, logging failures).

        @return: dict with "status" set to "stopped".
        """
        self._stop_eventsub()
        self._stop_tunnel()
        self._stop_scheduler()

        if self.overlay_manager.backend is not None:
            backend_stop = getattr(self.overlay_manager.backend, "stop", None)
            if callable(backend_stop):
                try:
                    backend_stop()
                except Exception:
                    logger.exception("Overlay backend stop failed")

        return {"status": "stopped"}

    def run(self) -> None:
        """
        @brief Blocking entry point for silent/production modes.

        Starts services, starts the webhook server (blocking), and waits for
        SIGINT. The webhook server must be listening before EventSub
        subscriptions are registered (Twitch verifies the callback immediately),
        so registration is deferred until after the server starts.

        @return: None
        """
        if self.mode is Mode.TEST:
            raise RuntimeError("run() is not available in test mode; use the REPL")

        if self.overlay_manager.backend is not None:
            backend_start = getattr(self.overlay_manager.backend, "start", None)
            if callable(backend_start):
                backend_start()

        self._run_startup_checks()
        self._start_scheduler()
        self._start_webhook(block=False)
        self._start_eventsub()

        self._running = True
        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("Interrupt received, shutting down.")
        finally:
            self.stop()

    def request_stop(self) -> None:
        """
        @brief Signal the blocking run loop to exit.

        Clears the _running flag so the next loop iteration in :meth:`run`
        returns and triggers shutdown via :meth:`stop`.

        @return: None
        """
        self._running = False

    def _start_scheduler(self) -> None:
        """
        @brief Create (if needed) and start the TimerScheduler for time triggers.

        Lazily instantiates a TimerScheduler bound to this bot and starts its
        periodic tick loop driving timer.* events.

        @return: None
        """
        from .scheduler import TimerScheduler

        if getattr(self, "_timer_scheduler", None) is None:
            self._timer_scheduler = TimerScheduler(self)
        self._timer_scheduler.start()

    def _stop_scheduler(self) -> None:
        """
        @brief Stop the TimerScheduler if one is currently running.

        @return: None
        """
        scheduler = getattr(self, "_timer_scheduler", None)
        if scheduler is not None:
            scheduler.stop()

    def _twitch_settings(self) -> dict[str, Any]:
        """
        @brief Return the "twitch" section of the loaded settings.

        @return: dict from settings["twitch"], or an empty dict when absent.
        """
        return self.settings.get("twitch", {}) or {}

    def _webhook_secret(self) -> str:
        """
        @brief Return the configured Twitch EventSub webhook secret.

        @return: the twitch.webhook_secret string, or "" when not set.
        """
        twitch = self._twitch_settings()
        return twitch.get("webhook_secret", "")

    def _run_startup_checks(self) -> None:
        """
        @brief Validate/refresh bot + channel tokens, fetch channel id, app token.

        Only runs in production. Silent/test modes skip all network calls.
        Each step is wrapped so a failure logs a warning without crashing.

        @return: None
        """
        if self.mode is not Mode.PRODUCTION:
            return
        if self._twitch_settings_obj is None or not getattr(self._twitch_settings_obj, "is_complete", lambda: False)():
            logger.info("Startup checks skipped (no complete TwitchSettings available).")
            return
        from .eventsub.app_token import AppTokenFetcher
        from .eventsub.channel_id import ChannelIdFetcher
        from .eventsub.token_refresher import TokenRefresher
        from .eventsub.token_validator import TokenValidator

        settings = self._twitch_settings_obj

        validator = TokenValidator()
        bot_info = validator.validate(settings.bot_oauth_token)
        if bot_info is None:
            logger.warning("Bot token invalid; attempting refresh.")
            refresher = TokenRefresher()
            refreshed = refresher.refresh(
                settings.bot_refresh_token,
                settings.bot_client_id,
                settings.bot_client_secret,
                twitch_settings=settings,
                prefix="BOT",
            )
            if refreshed is None:
                logger.error("Bot token refresh failed. Run scripts/get_all_scopes.py to re-authenticate.")
            else:
                settings.reload()
        else:
            bot_user_id = bot_info.get("user_id", "")
            if bot_user_id and not settings.bot_channel_id:
                settings.write_env({"BOT_CHANNEL_ID": bot_user_id})
                settings.reload()

        channel_info = validator.validate(settings.channel_oauth_token) if settings.channel_oauth_token else None
        if channel_info is None and settings.channel_oauth_token:
            logger.warning("Channel token invalid; attempting refresh.")
            refresher = TokenRefresher()
            refresher.refresh(
                settings.channel_refresh_token,
                settings.channel_client_id,
                settings.bot_client_secret,
                twitch_settings=settings,
                prefix="CHANNEL",
            )
            settings.reload()
        elif channel_info:
            channel_user_id = channel_info.get("user_id", "")
            if channel_user_id and not settings.twitch_channel_id:
                settings.write_env({"TWITCH_CHANNEL_ID": channel_user_id})
                settings.reload()

        if not settings.twitch_channel_id and settings.twitch_channel:
            fetcher = ChannelIdFetcher()
            channel_id = fetcher.fetch(settings.bot_oauth_token, settings.bot_client_id, settings.twitch_channel)
            if channel_id:
                settings.write_env({"TWITCH_CHANNEL_ID": channel_id})
                settings.reload()

        try:
            app_fetcher = AppTokenFetcher()
            self._app_access_token = app_fetcher.fetch(settings.bot_client_id, settings.bot_client_secret)
            self._app_token_fetcher = app_fetcher
        except Exception:
            logger.exception("App access token fetch failed; EventSub subscription will be skipped.")

    def _resolve_webhook_port(self) -> int:
        """
        @brief Resolve and cache the webhook port (shared by tunnel + server).

        Both :meth:`_start_webhook` (binds the Flask server) and
        :meth:`_start_tunnel` (forwards the port to cloudflared) need the same
        webhook port. Resolving twice would re-run the freedom check AFTER the
        server has already bound the port (which would then look "in use" by
        itself), so the port is resolved once and cached on ``self._webhook_port``.

        @return: the resolved webhook port (also stored on self._webhook_port).
        """
        if self._webhook_port is not None:
            return self._webhook_port
        runtime = self.settings.get("runtime", {}) or {}
        webhook_cfg = runtime.get("webhook", {}) or {}
        host = webhook_cfg.get("host", "127.0.0.1")
        port = resolve_port_or_exit(
            "webhook",
            self.settings,
            self._settings_path,
            interactive=_is_interactive(),
            host=host,
        )
        self._webhook_port = port
        return port

    def _start_tunnel(self) -> str | None:
        """
        @brief Start the cloudflared Quick Tunnel (production only).

        Returns the cached public_url when a tunnel is already running;
        otherwise starts a new TunnelManager for the configured webhook port
        and stores it on self._tunnel_manager. Returns None in non-production
        modes or when the tunnel fails to start.

        @return: the public https trycloudflare URL, or None on failure/skip.
        """
        if self.mode is not Mode.PRODUCTION:
            return None
        if self._tunnel_manager is not None:
            return getattr(self._tunnel_manager, "public_url", "") or None
        port = self._resolve_webhook_port()
        manager = TunnelManager()
        try:
            public_url = manager.start(local_port=port)
        except Exception:
            logger.exception("cloudflared tunnel failed to start; EventSub callbacks will not work.")
            manager.stop()
            return None
        self._tunnel_manager = manager
        return public_url

    def _stop_tunnel(self) -> None:
        """
        @brief Stop the cloudflared tunnel if one is running and clear the handle.

        @return: None
        """
        if self._tunnel_manager is not None:
            try:
                self._tunnel_manager.stop()
            except Exception:
                logger.exception("Tunnel stop failed")
            self._tunnel_manager = None

    def _start_webhook(self, *, block: bool = False) -> Any:
        """
        @brief Start the EventSub webhook server (Flask) on the configured port.

        Reads twitch.webhook_secret and the runtime.webhook host/port from
        settings. Warns and returns None when the secret is missing (Twitch
        cannot verify signatures without it). When block is True the server
        runs in the foreground; otherwise it runs in a background thread.

        @param block: when True the call blocks running the server; False
            starts it in a background thread.
        @return: the webhook server handle (or None if the secret is missing).
        """
        webhook_secret = self._webhook_secret()
        runtime = self.settings.get("runtime", {}) or {}
        webhook_cfg = runtime.get("webhook", {}) or {}
        host = webhook_cfg.get("host", "127.0.0.1")
        port = self._resolve_webhook_port()
        if not webhook_secret:
            logger.warning("twitch.webhook_secret not set; EventSub webhook cannot verify signatures.")
            return None

        from .eventsub.server import run_webhook_server

        self._webhook_server = run_webhook_server(
            self,
            webhook_secret,
            host=host,
            port=port,
            block=block,
        )
        return self._webhook_server

    def _stop_webhook(self) -> None:
        """
        @brief Shut down the EventSub webhook server if it is running.

        Calls the server's shutdown method (when present) best-effort and
        clears the stored handle.

        @return: None
        """
        server = getattr(self, "_webhook_server", None)
        if server is None:
            return
        shutdown = getattr(server, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                logger.exception("Webhook server shutdown failed")
        self._webhook_server = None

    def _start_eventsub(self) -> None:
        """
        @brief Build the EventSubClient and register subscriptions (production).

        In non-production modes this only logs that registration is skipped.
        In production it constructs an EventSubClient from TwitchSettings (or a
        settings dict fallback), sets the callback URL and webhook secret, then
        registers the subscription types required by the configured triggers.

        @return: None
        """
        if self.mode is not Mode.PRODUCTION:
            logger.info("EventSub subscription registration skipped in %s mode.", self.mode.value)
            return

        settings_obj = self._twitch_settings_obj
        client_id = settings_obj.bot_client_id if settings_obj is not None else self._twitch_settings().get("client_id", "")
        if not client_id:
            logger.info("EventSub credentials incomplete; skipping subscription registration.")
            return

        from .eventsub.client import EventSubClient

        app_token_fetcher = getattr(self, "_app_token_fetcher", None)
        if settings_obj is not None:
            self._eventsub_client = EventSubClient(
                settings_obj,
                app_token_fetcher=app_token_fetcher,
            )
        else:
            self._eventsub_client = EventSubClient(self._twitch_settings(), app_token_fetcher=app_token_fetcher)

        callback_url = self._build_callback_url()
        if callback_url:
            self._eventsub_client.set_callback_url(callback_url)
            if settings_obj is not None:
                self._eventsub_client.webhook_secret = self._webhook_secret()
        else:
            self._eventsub_client.webhook_secret = self._webhook_secret()
            if not self._eventsub_client.callback_url:
                logger.info("No callback_url available; skipping EventSub subscription registration.")
                return

        subscription_types = self._eventsub_client.subscription_types_for_triggers(
            self.settings.get("triggers", [])
        )
        try:
            self._eventsub_client.register_subscriptions(subscription_types)
        except Exception:
            logger.exception("EventSub subscription registration failed")

    def _build_callback_url(self) -> str:
        """
        @brief Build the public EventSub callback URL.

        Uses the cloudflared tunnel public URL (suffixing "/eventsub") when a
        tunnel is available; otherwise falls back to the callback_url stored
        in the twitch settings section (may be empty).

        @return: the callback URL string (possibly "" when nothing is configured).
        """
        public_url = self._start_tunnel() or ""
        if public_url:
            return public_url.rstrip("/") + "/eventsub"
        twitch = self._twitch_settings()
        existing = twitch.get("callback_url", "")
        return existing

    def _stop_eventsub(self) -> None:
        """
        @brief Delete EventSub subscriptions and stop the webhook server.

        Best-effort deletes the registered subscriptions via the EventSubClient
        (logging failures), clears the client handle, then shuts down the
        webhook server.

        @return: None
        """
        client = getattr(self, "_eventsub_client", None)
        if client is not None:
            try:
                client.delete_subscriptions()
            except Exception:
                logger.exception("EventSub subscription deletion failed")
            self._eventsub_client = None
        self._stop_webhook()

    def handle_event(self, event_name: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        @brief Process an inbound event through triggers and features.

        In silent mode the event is first captured by the SilentEventCollector.
        The trigger resolver matches the configured triggers against the
        event/payload, feature reactions are merged in, and the ReactionEngine
        executes the combined reaction list.

        @param event_name: name of the event to handle (e.g. "command",
            "timer.tick", "channel_point_reward").
        @param payload: event payload dict (roles, args, broadcaster_id, ...);
            None is treated as an empty dict.
        @return: list of reaction result dicts produced by the ReactionEngine.
        """
        payload = payload or {}

        if self.mode is Mode.SILENT and self.silent_collector is not None:
            self.silent_collector.collect(event_name, payload)

        reactions: list[dict[str, Any]] = []

        self.trigger_resolver.triggers = self.settings.get("triggers", [])
        trigger_reactions = self.trigger_resolver.resolve(event_name, payload)
        if trigger_reactions:
            reactions.extend(trigger_reactions)

        features = self.feature_manager.dispatch(event_name, payload)
        for value in features.values():
            if isinstance(value, list):
                reactions.extend(value)

        results = self.reaction_engine.execute(reactions, context={"event_name": event_name, **payload})

        # Record last-seen AFTER trigger resolution so a `new_chatter`
        # (inactivity-window) leaf compares against the PREVIOUS message
        # time, not the current one (which would make the window ~0s and the
        # leaf essentially never match).
        if event_name == "chat.message":
            channel = payload.get("channel", "") or ""
            username = payload.get("username", payload.get("user_name", "")) or ""
            if channel and username:
                self._chatter_tracker.record(channel, username, self.trigger_resolver._time_provider())

        return results

    @property
    def sent(self) -> list[Any]:
        """
        @brief Return the in-memory log of side-effects produced in test/silent.

        @return: the list self._sent of recorded side-effect tuples.
        """
        return self._sent

    def _send_chat(self, channel: str, message: str) -> dict[str, Any]:
        """
        @brief Production chat send stub (not yet wired to IRC/Helix).

        Returns a descriptive dict instead of performing a real send. Wire up
        Twitch IRC/Helix chat.postMessage here to enable real outbound chat.

        @param channel: target channel identifier for the message.
        @param message: chat message text to send.
        @return: dict describing the would-be chat send (type/channel/message).
        """
        # Production chat send is currently a stub; wire up Twitch IRC/Helix
        # chat.postMessage here to enable real outbound chat.
        return {"type": "chat_send", "channel": channel, "message": message}

    def _create_clip(self) -> str:
        """
        @brief Production clip creation stub (not yet wired to Helix).

        Returns an empty string instead of creating a clip. Wire up the Helix
        create clip endpoint here to enable real clip creation.

        @return: empty string placeholder for the created clip id/url.
        """
        # Production clip creation is currently a stub; wire up the Helix
        # create clip endpoint here to enable real clip creation.
        return ""

    def _noop_counter(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        @brief No-op counter handler returning a descriptive dict.

        Used as a fallback when no real counter handler is wired, preserving
        the call signature so callers can be swapped in later.

        @param action: counter action name that was requested.
        @param payload: counter action payload dict.
        @return: dict echoing the counter_noop type, action and payload.
        """
        return {"type": "counter_noop", "action": action, "payload": payload}

    def _noop_moderation(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        @brief No-op moderation handler returning a descriptive dict.

        Used as a fallback when no real moderation handler is wired,
        preserving the call signature so callers can be swapped in later.

        @param action: moderation action name that was requested.
        @param payload: moderation action payload dict.
        @return: dict echoing the moderation_noop type, action and payload.
        """
        return {"type": "moderation_noop", "action": action, "payload": payload}

    def _noop_streampet(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        @brief No-op streampet handler returning a descriptive dict.

        Used as a fallback when no real streampet handler is wired, preserving
        the call signature so callers can be swapped in later.

        @param payload: streampet action payload dict.
        @return: dict echoing the streampet_noop type and payload.
        """
        return {"type": "streampet_noop", "payload": payload}
