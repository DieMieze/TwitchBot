import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.mode import Mode
from twitchbot_runtime.twitch_api import ChannelInfoFetcher, ChatSender, ClipCreator, ModerationActor, TwitchApiClient
from twitchbot_runtime.twitch_settings import TwitchSettings


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


class FakeSession:
    def __init__(self):
        self.requests = []
        self.responses: list[FakeResponse] = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        self.requests.append({
            "method": method,
            "url": url,
            "params": params,
            "json": json,
            "headers": headers,
        })
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(200, {"data": []})

    def queue(self, response):
        self.responses.append(response)


def _settings(tmp_path, **overrides):
    settings = TwitchSettings(tmp_path / ".env")
    settings.write_env({
        "BOT_CLIENT_ID": "cid",
        "BOT_CLIENT_SECRET": "csecret",
        "BOT_USERNAME": "bot",
        "TWITCH_CHANNEL": "streamer",
        "TWITCH_CHANNEL_ID": "999",
        "BOT_CHANNEL_ID": "111",
        "BOT_OAUTH_TOKEN": "tok",
    })
    for key, value in overrides.items():
        settings.write_env({key: value})
    settings.reload()
    return settings


def test_chatsender_silent_mode_returns_noop_without_network(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    client = TwitchApiClient(settings, mode=Mode.SILENT, http_session=session)
    sender = ChatSender(client)

    result = sender.send("999", "hi")

    assert result["status"] == "noop"
    assert session.requests == []


def test_chatsender_production_posts_to_helix(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"message_id": "m1"}]}))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    sender = ChatSender(client)

    result = sender.send("999", "hello")

    assert result["status"] == "sent"
    req = session.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith("/chat/messages")
    assert req["json"]["broadcaster_id"] == "999"
    assert req["json"]["sender_id"] == "111"
    assert req["json"]["message"] == "hello"


def test_chatsender_empty_broadcaster_id_returns_error(tmp_path):
    settings = _settings(tmp_path)
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=FakeSession())
    sender = ChatSender(client)

    result = sender.send("", "hello")

    assert result["status"] == "error"


def test_moderationactor_resolve_user_id_numeric_direct(tmp_path):
    settings = _settings(tmp_path)
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=FakeSession())
    actor = ModerationActor(client)

    assert actor._resolve_user_id("12345") == "12345"


def test_moderationactor_resolve_user_id_caches_login_lookup(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"id": "777", "login": "spammer"}]}))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    actor = ModerationActor(client)

    first = actor._resolve_user_id("spammer")
    second = actor._resolve_user_id("spammer")

    assert first == "777"
    assert second == "777"
    login_requests = [r for r in session.requests if r["method"] == "GET" and r["params"] == {"login": "spammer"}]
    assert len(login_requests) == 1


def test_moderationactor_resolve_user_id_returns_empty_on_404(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(404))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    actor = ModerationActor(client)

    assert actor._resolve_user_id("nobody") == ""


def test_moderationactor_ban_production_resolves_and_posts(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"id": "555", "login": "spammer"}]}))
    session.queue(FakeResponse(200, {"data": [{"id": "ban-record"}]}))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    actor = ModerationActor(client)

    result = actor.ban("spammer", reason="test")

    assert result["status"] == "executed"
    ban_req = [r for r in session.requests if r["method"] == "POST" and r["url"].endswith("/moderation/bans")][0]
    assert ban_req["params"]["broadcaster_id"] == "999"
    assert ban_req["params"]["moderator_id"] == "111"
    assert ban_req["json"]["data"]["user_id"] == "555"
    assert ban_req["json"]["data"]["reason"] == "test"


def test_moderationactor_timeout_sends_duration(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"id": "555", "login": "spammer"}]}))
    session.queue(FakeResponse(200, {"data": [{}]}))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    actor = ModerationActor(client)

    result = actor.timeout("spammer", 600)

    assert result["status"] == "executed"
    ban_req = [r for r in session.requests if r["method"] == "POST" and r["url"].endswith("/moderation/bans")][0]
    assert ban_req["json"]["data"]["duration"] == 600


def test_moderationactor_silent_mode_noop_without_network(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    client = TwitchApiClient(settings, mode=Mode.SILENT, http_session=session)
    actor = ModerationActor(client)

    result = actor.ban("spammer")

    assert result["status"] == "noop"
    assert session.requests == []


def test_moderationactor_ban_empty_target_returns_error(tmp_path):
    settings = _settings(tmp_path)
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=FakeSession())
    actor = ModerationActor(client)

    result = actor.ban("")

    assert result["status"] == "error"
    assert result["error"] == "missing_target"


def test_clipcreator_silent_mode_returns_empty(tmp_path):
    settings = _settings(tmp_path)
    client = TwitchApiClient(settings, mode=Mode.SILENT, http_session=FakeSession())
    creator = ClipCreator(client)

    assert creator.create() == ""


def test_clipcreator_production_posts_with_channel_id(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(202, {"data": [{"id": "clip1", "edit_url": "https://clips.twitch.tv/clip1"}]}))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    creator = ClipCreator(client)

    url = creator.create(title="Test clip")

    assert url == "https://clips.twitch.tv/clip1"
    req = session.requests[0]
    assert req["method"] == "POST"
    assert req["url"].endswith("/clips")
    assert req["params"]["broadcaster_id"] == "999"


def test_clipcreator_empty_channel_id_returns_empty(tmp_path):
    settings = _settings(tmp_path, TWITCH_CHANNEL_ID="")
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=FakeSession())
    creator = ClipCreator(client)

    assert creator.create() == ""


def test_channelinfo_silent_mode_returns_empty(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    client = TwitchApiClient(settings, mode=Mode.SILENT, http_session=session)
    fetcher = ChannelInfoFetcher(client)

    assert fetcher.game_name() == ""
    assert session.requests == []


def test_channelinfo_production_returns_game_name(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"game_name": "Minecraft"}]}))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    fetcher = ChannelInfoFetcher(client)

    assert fetcher.game_name() == "Minecraft"
    req = session.requests[0]
    assert req["method"] == "GET"
    assert req["url"].endswith("/channels")
    assert req["params"]["broadcaster_id"] == "999"


def test_channelinfo_caches_within_ttl(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(200, {"data": [{"game_name": "Minecraft"}]}))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    fetcher = ChannelInfoFetcher(client, cache_ttl=60.0)

    assert fetcher.game_name() == "Minecraft"
    assert fetcher.game_name() == "Minecraft"

    assert len(session.requests) == 1


def test_channelinfo_empty_channel_id_returns_empty(tmp_path):
    settings = _settings(tmp_path, TWITCH_CHANNEL_ID="")
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=FakeSession())
    fetcher = ChannelInfoFetcher(client)

    assert fetcher.game_name() == ""


def test_channelinfo_error_response_returns_empty(tmp_path):
    settings = _settings(tmp_path)
    session = FakeSession()
    session.queue(FakeResponse(500, text="server error"))
    client = TwitchApiClient(settings, mode=Mode.PRODUCTION, http_session=session)
    fetcher = ChannelInfoFetcher(client)

    assert fetcher.game_name() == ""
