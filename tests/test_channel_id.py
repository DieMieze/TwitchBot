import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.eventsub.channel_id import ChannelIdFetcher


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.response


def test_fetch_returns_user_id_when_found():
    session = FakeSession(FakeResponse(200, {"data": [{"id": "98765", "login": "streamer"}]}))
    fetcher = ChannelIdFetcher(http_session=session)

    assert fetcher.fetch("token", "cid", "streamer") == "98765"
    assert session.calls[0]["params"] == {"login": "streamer"}


def test_fetch_returns_none_when_not_found():
    session = FakeSession(FakeResponse(200, {"data": []}))
    fetcher = ChannelIdFetcher(http_session=session)

    assert fetcher.fetch("token", "cid", "nobody") is None


def test_fetch_returns_none_on_404():
    session = FakeSession(FakeResponse(404))
    fetcher = ChannelIdFetcher(http_session=session)

    assert fetcher.fetch("token", "cid", "nobody") is None


def test_fetch_returns_none_without_inputs():
    fetcher = ChannelIdFetcher(http_session=FakeSession(FakeResponse(200)))

    assert fetcher.fetch("", "cid", "x") is None
    assert fetcher.fetch("t", "", "x") is None
    assert fetcher.fetch("t", "cid", "") is None
