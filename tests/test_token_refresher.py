import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.eventsub.token_refresher import TokenRefresher
from twitchbot_runtime.twitch_settings import TwitchSettings


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.posts.append({"url": url, "data": data})
        return self.response


def test_refresh_success_returns_tokens_and_persists(tmp_path):
    session = FakeSession(FakeResponse(200, {"access_token": "new-access", "refresh_token": "new-refresh"}))
    settings = TwitchSettings(tmp_path / ".env")
    refresher = TokenRefresher(http_session=session)

    result = refresher.refresh("old-refresh", "cid", "csecret", twitch_settings=settings, prefix="BOT")

    assert result == ("new-access", "new-refresh")
    settings.reload()
    assert settings.bot_oauth_token == "new-access"
    assert settings.bot_refresh_token == "new-refresh"
    assert session.posts[0]["data"]["grant_type"] == "refresh_token"


def test_refresh_failure_returns_none(tmp_path):
    session = FakeSession(FakeResponse(400, text="bad"))
    refresher = TokenRefresher(http_session=session)

    assert refresher.refresh("bad", "cid", "csecret") is None


def test_refresh_without_required_inputs_returns_none():
    refresher = TokenRefresher(http_session=FakeSession(FakeResponse(200, {})))

    assert refresher.refresh("", "cid", "csecret") is None
    assert refresher.refresh("r", "", "csecret") is None
    assert refresher.refresh("r", "cid", "") is None


def test_refresh_reuses_existing_refresh_token_when_missing_in_response(tmp_path):
    session = FakeSession(FakeResponse(200, {"access_token": "new-access"}))
    settings = TwitchSettings(tmp_path / ".env")
    refresher = TokenRefresher(http_session=session)

    result = refresher.refresh("keep-refresh", "cid", "csecret", twitch_settings=settings)

    assert result == ("new-access", "keep-refresh")
