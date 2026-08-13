import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.eventsub.app_token import AppTokenFetcher


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, url, data=None, timeout=None):
        self.posts.append({"url": url, "data": data})
        return self.response


def test_fetch_returns_and_caches_token():
    session = FakeSession(FakeResponse(200, {"access_token": "app-tok-123"}))
    fetcher = AppTokenFetcher(http_session=session)

    token = fetcher.fetch("cid", "csecret")
    token_again = fetcher.fetch("cid", "csecret")

    assert token == "app-tok-123"
    assert token_again == token
    assert len(session.posts) == 1
    assert session.posts[0]["data"]["grant_type"] == "client_credentials"


def test_fetch_raises_without_credentials():
    fetcher = AppTokenFetcher(http_session=FakeSession(FakeResponse(200)))

    try:
        fetcher.fetch("", "csecret")
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_clear_cache_forces_refetch():
    session = FakeSession(FakeResponse(200, {"access_token": "tok-1"}))
    fetcher = AppTokenFetcher(http_session=session)

    fetcher.fetch("cid", "csecret")
    fetcher.clear_cache()
    fetcher.fetch("cid", "csecret")

    assert len(session.posts) == 2
