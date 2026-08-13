import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.eventsub.client import EventSubClient
from twitchbot_runtime.twitch_settings import TwitchSettings


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self):
        self.posts = []
        self.deletes = []
        self.token_response = FakeResponse(
            200, {"access_token": "fake-token-123"}
        )
        self.subscription_responses = []

    def post(self, url, data=None, headers=None, json=None, timeout=None):
        self.posts.append({"url": url, "data": data, "headers": headers, "json": json})
        if "oauth2/token" in url:
            return self.token_response
        if self.subscription_responses:
            return self.subscription_responses.pop(0)
        return FakeResponse(202, {"data": [{"id": "sub-id"}]})

    def delete(self, url, headers=None, timeout=None):
        self.deletes.append({"url": url, "headers": headers})
        return FakeResponse(204)


def _make_client():
    twitch = {
        "client_id": "cid",
        "client_secret": "csecret",
        "webhook_secret": "wsecret",
        "callback_url": "https://example.com/eventsub",
        "broadcaster_user_id": "42",
        "bot_user_id": "7",
    }
    client = EventSubClient(twitch, http_session=FakeSession())
    return client


def _make_settings_client(tmp_path):
    settings = TwitchSettings(tmp_path / ".env")
    settings.write_env({
        "BOT_CLIENT_ID": "cid",
        "BOT_CLIENT_SECRET": "csecret",
        "BOT_USERNAME": "bot",
        "TWITCH_CHANNEL": "streamer",
        "TWITCH_CHANNEL_ID": "42",
        "BOT_CHANNEL_ID": "7",
    })
    return EventSubClient(settings, http_session=FakeSession())


def test_subscription_types_for_triggers_includes_command_and_defaults():
    client = _make_client()
    triggers = [
        {
            "name": "hello",
            "when": {
                "kind": "and",
                "children": [
                    {"kind": "leaf", "condition": {"type": "command", "command": "!hello"}}
                ],
            },
        }
    ]

    types = client.subscription_types_for_triggers(triggers)

    assert "channel.chat.message" in types
    assert "channel.follow" in types
    assert "channel.raid" in types
    assert "channel.subscribe" in types
    assert "channel.cheer" in types


def test_fetch_app_access_token_caches_token():
    client = _make_client()

    token = client.fetch_app_access_token()
    token_again = client.fetch_app_access_token()

    assert token == "fake-token-123"
    assert token_again == token
    assert sum(1 for p in client._http.posts if "oauth2/token" in p["url"]) == 1


def test_register_subscriptions_posts_correct_payload():
    client = _make_client()

    ids = client.register_subscriptions(["channel.follow", "channel.cheer"])

    assert ids == ["sub-id", "sub-id"]
    sub_posts = [p for p in client._http.posts if "event_sub/subscriptions" in p["url"]]
    assert len(sub_posts) == 2
    first = sub_posts[0]["json"]
    assert first["type"] == "channel.follow"
    assert first["version"] == "2"
    assert first["transport"]["method"] == "webhook"
    assert first["transport"]["callback"] == "https://example.com/eventsub"
    assert first["transport"]["secret"] == "wsecret"


def test_delete_subscriptions_clears_ids():
    client = _make_client()
    client.register_subscriptions(["channel.follow"])

    assert client.subscription_ids == ["sub-id"]

    client.delete_subscriptions()

    assert client.subscription_ids == []
    assert len(client._http.deletes) == 1


def test_register_subscriptions_logs_failed_subscription():
    client = _make_client()
    client._http.subscription_responses = [FakeResponse(400, text="bad")]

    ids = client.register_subscriptions(["channel.follow"])

    assert ids == []


def test_condition_for_chat_uses_bot_user_id():
    client = _make_client()

    condition = client._condition_for("channel.chat.message")

    assert condition == {"broadcaster_user_id": "42", "user_id": "7"}


def test_condition_for_follow_uses_bot_as_moderator():
    client = _make_client()

    condition = client._condition_for("channel.follow")

    assert condition == {"broadcaster_user_id": "42", "moderator_user_id": "7"}


def test_condition_for_raid_uses_to_broadcaster_user_id():
    client = _make_client()

    condition = client._condition_for("channel.raid")

    assert condition == {"to_broadcaster_user_id": "42"}


def test_twitch_settings_client_uses_bot_channel_id(tmp_path):
    client = _make_settings_client(tmp_path)

    assert client.client_id == "cid"
    assert client.broadcaster_user_id == "42"
    assert client.bot_user_id == "7"
    assert client._condition_for("channel.chat.message") == {"broadcaster_user_id": "42", "user_id": "7"}


def test_app_token_fetcher_injection(tmp_path):
    class FakeFetcher:
        def __init__(self):
            self.calls = 0

        def fetch(self, client_id, client_secret):
            self.calls += 1
            return "injected-app-token"

    fetcher = FakeFetcher()
    client = EventSubClient(_make_dict(), http_session=FakeSession(), app_token_fetcher=fetcher)

    token = client.fetch_app_access_token()

    assert token == "injected-app-token"
    assert fetcher.calls == 1


def _make_dict():
    return {
        "client_id": "cid",
        "client_secret": "csecret",
        "webhook_secret": "wsecret",
        "callback_url": "https://example.com/eventsub",
        "broadcaster_user_id": "42",
        "bot_user_id": "7",
    }
