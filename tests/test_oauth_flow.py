import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.eventsub.oauth_flow import OAuthFlowStarter


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, url, data=None, timeout=None):
        self.posts.append({"url": url, "data": data})
        return self.response


def test_build_url_includes_client_id_scopes_redirect():
    url = OAuthFlowStarter.build_url("cid123", ["user:read:chat", "clips:edit"], "http://localhost:5003/oauth/callback")

    assert "client_id=cid123" in url
    # build_url URL-encodes spaces as %20 (Twitch accepts this); decode to assert intent.
    assert "scope=user:read:chat clips:edit" in unquote(url)
    assert "redirect_uri=http://localhost:5003/oauth/callback" in url
    assert "response_type=code" in url


def test_exchange_success_returns_tokens():
    session = FakeSession(FakeResponse(200, {"access_token": "acc", "refresh_token": "ref"}))
    flow = OAuthFlowStarter(http_session=session)

    result = flow.exchange("code123", "cid", "csecret", "http://localhost:5003/oauth/callback")

    assert result == ("acc", "ref")
    assert session.posts[0]["data"]["code"] == "code123"
    assert session.posts[0]["data"]["grant_type"] == "authorization_code"


def test_exchange_failure_returns_none():
    session = FakeSession(FakeResponse(400))
    flow = OAuthFlowStarter(http_session=session)

    assert flow.exchange("bad", "cid", "csecret") is None


def test_exchange_returns_none_without_required_inputs():
    flow = OAuthFlowStarter(http_session=FakeSession(FakeResponse(200)))

    assert flow.exchange("", "cid", "csecret") is None
    assert flow.exchange("code", "", "csecret") is None
    assert flow.exchange("code", "cid", "") is None


def test_start_and_wait_uses_provided_secret_without_prompt(monkeypatch):
    captured = {}

    def fake_flask(self, redirect_uri, client_id, port, client_secret=""):
        captured["client_secret"] = client_secret
        captured["called"] = True
        captured["port"] = port
        captured["redirect_uri"] = redirect_uri
        return ("acc", "ref")

    monkeypatch.setattr(OAuthFlowStarter, "_run_flask_callback", fake_flask)
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("input() must not be called")))

    flow = OAuthFlowStarter(http_session=FakeSession(FakeResponse(200, {"access_token": "acc", "refresh_token": "ref"})))

    result = flow.start_and_wait("cid", ["user:read:chat"], "http://localhost:5010/oauth/callback", port=5010, client_secret="topsecret")

    assert captured["called"]
    assert captured["client_secret"] == "topsecret"
    assert captured["port"] == 5010
    assert captured["redirect_uri"] == "http://localhost:5010/oauth/callback"
    assert result == ("acc", "ref")
