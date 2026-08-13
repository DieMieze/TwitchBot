import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.bot import TwitchBot


class FakeTwitchSettings:
    def __init__(self, complete=True):
        self.bot_client_id = "cid"
        self.bot_client_secret = "csecret"
        self.bot_oauth_token = "tok"
        self.bot_refresh_token = "rtok"
        self.bot_channel_id = "111"
        self.twitch_channel = "streamer"
        self.twitch_channel_id = "999"
        self.channel_oauth_token = "ctok"
        self.channel_refresh_token = "crtok"
        self.channel_client_id = "cid"
        self._complete = complete
        self.written: dict[str, str] = {}

    def is_complete(self):
        return self._complete

    def missing_bot_keys(self):
        return [] if self._complete else ["BOT_CLIENT_ID"]

    def reload(self):
        pass

    def write_env(self, updates):
        self.written.update(updates)


def _patch_startup(monkeypatch, *, settings=None, valid_bot=True, valid_channel=True, channel_id=None):
    settings = settings or FakeTwitchSettings()

    monkeypatch.setattr(
        "twitchbot_runtime.twitch_settings.TwitchSettings.load",
        lambda env_path=None: settings,
    )
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._setup_twitch_api",
        lambda self: setattr(self, "_twitch_settings_obj", settings),
    )

    def fake_validate(token):
        if not token:
            return None
        if token == "tok" and valid_bot:
            return {"user_id": "111", "client_id": "cid", "scopes": ["user:write:chat"], "expires_in": 1000}
        if token == "ctok" and valid_channel:
            return {"user_id": "999", "client_id": "cid", "scopes": ["channel:bot"], "expires_in": 1000}
        return None

    monkeypatch.setattr(
        "twitchbot_runtime.eventsub.token_validator.TokenValidator.validate",
        lambda self, token: fake_validate(token),
    )
    def _refresh(self, refresh_token, client_id, client_secret, twitch_settings=None, prefix="BOT"):
        if twitch_settings is not None:
            twitch_settings.write_env({
                f"{prefix}_OAUTH_TOKEN": "new-access",
                f"{prefix}_REFRESH_TOKEN": "new-refresh",
            })
        return ("new-access", "new-refresh")

    monkeypatch.setattr(
        "twitchbot_runtime.eventsub.token_refresher.TokenRefresher.refresh",
        _refresh,
    )

    class FakeChannelIdFetcher:
        def fetch(self, access_token, client_id, login):
            return channel_id

    monkeypatch.setattr(
        "twitchbot_runtime.eventsub.channel_id.ChannelIdFetcher",
        FakeChannelIdFetcher,
    )

    class FakeAppTokenFetcher:
        def __init__(self):
            self.calls = 0

        def fetch(self, client_id, client_secret):
            self.calls += 1
            return "app-tok-123"

    fake_app = FakeAppTokenFetcher()

    def fake_app_cls():
        return fake_app

    monkeypatch.setattr(
        "twitchbot_runtime.eventsub.app_token.AppTokenFetcher",
        fake_app_cls,
    )
    return settings, fake_app


def test_startup_checks_in_production_validates_and_fetches_app_token(monkeypatch):
    _patch_startup(monkeypatch)
    monkeypatch.setattr(TwitchBot, "_start_webhook", lambda self, block=False: None)
    monkeypatch.setattr(TwitchBot, "_start_eventsub", lambda self: None)
    monkeypatch.setattr(TwitchBot, "_start_tunnel", lambda self: None)

    bot = TwitchBot(settings_path=None, execution_mode="production")
    bot.start()
    bot.stop()

    assert getattr(bot, "_app_access_token", None) == "app-tok-123"


def test_startup_checks_skipped_in_silent_mode(monkeypatch):
    _patch_startup(monkeypatch)
    monkeypatch.setattr(TwitchBot, "_start_webhook", lambda self, block=False: None)
    monkeypatch.setattr(TwitchBot, "_start_eventsub", lambda self: None)
    monkeypatch.setattr(TwitchBot, "_start_tunnel", lambda self: None)

    bot = TwitchBot(settings_path=None, execution_mode="silent")
    bot.start()

    assert getattr(bot, "_app_access_token", None) is None
    bot.stop()


def test_startup_checks_refresh_bot_token_when_invalid(monkeypatch):
    settings, _app = _patch_startup(monkeypatch, valid_bot=False)
    monkeypatch.setattr(TwitchBot, "_start_webhook", lambda self, block=False: None)
    monkeypatch.setattr(TwitchBot, "_start_eventsub", lambda self: None)
    monkeypatch.setattr(TwitchBot, "_start_tunnel", lambda self: None)

    bot = TwitchBot(settings_path=None, execution_mode="production")
    bot.start()
    bot.stop()

    assert "BOT_OAUTH_TOKEN" in settings.written
    assert settings.written["BOT_OAUTH_TOKEN"] == "new-access"


def test_startup_checks_falls_back_to_channel_id_fetcher(monkeypatch, tmp_path):
    settings = FakeTwitchSettings()
    settings.twitch_channel_id = ""
    _patch_startup(monkeypatch, settings=settings, channel_id="888")
    monkeypatch.setattr(TwitchBot, "_start_webhook", lambda self, block=False: None)
    monkeypatch.setattr(TwitchBot, "_start_eventsub", lambda self: None)
    monkeypatch.setattr(TwitchBot, "_start_tunnel", lambda self: None)

    bot = TwitchBot(settings_path=None, execution_mode="production")
    bot.start()
    bot.stop()

    assert settings.written.get("TWITCH_CHANNEL_ID") == "888"


def test_start_eventsub_uses_tunnel_callback_url(monkeypatch):
    _patch_startup(monkeypatch)
    monkeypatch.setattr(TwitchBot, "_start_webhook", lambda self, block=False: None)

    captured = {}

    class FakeEventSubClient:
        def __init__(self, twitch_settings, http_session=None, app_token_fetcher=None):
            captured["settings"] = twitch_settings
            captured["fetcher"] = app_token_fetcher
            self.callback_url = ""
            self.webhook_secret = ""

        def set_callback_url(self, url):
            captured["callback_url"] = url

        def subscription_types_for_triggers(self, triggers):
            return ["channel.follow"]

        def register_subscriptions(self, types):
            captured["registered"] = types
            return []

        def delete_subscriptions(self):
            pass

    monkeypatch.setattr(TwitchBot, "_start_tunnel", lambda self: "https://abc.trycloudflare.com")
    import twitchbot_runtime.eventsub.client as client_mod

    monkeypatch.setattr(client_mod, "EventSubClient", FakeEventSubClient, raising=True)
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._start_eventsub",
        TwitchBot._start_eventsub,
        raising=True,
    )

    bot = TwitchBot(settings_path=None, execution_mode="production")
    bot.start()
    bot.stop()

    assert captured.get("callback_url") == "https://abc.trycloudflare.com/eventsub"
    assert captured.get("registered") == ["channel.follow"]


def test_start_eventsub_skipped_in_silent_mode(monkeypatch):
    _patch_startup(monkeypatch)
    monkeypatch.setattr(TwitchBot, "_start_webhook", lambda self, block=False: None)

    bot = TwitchBot(settings_path=None, execution_mode="silent")
    bot.start()

    assert bot._eventsub_client is None
    bot.stop()
