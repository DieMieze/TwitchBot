import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.eventsub.token_validator import TokenValidator


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
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers})
        return self.response


def test_validate_returns_payload_on_200():
    session = FakeSession(FakeResponse(200, {"user_id": "42", "client_id": "cid", "scopes": ["a", "b"], "expires_in": 1000}))
    validator = TokenValidator(http_session=session)

    result = validator.validate("token-abc")

    assert result is not None
    assert result["user_id"] == "42"
    assert result["scopes"] == ["a", "b"]
    assert session.calls[0]["headers"]["Authorization"] == "Bearer token-abc"


def test_validate_returns_none_on_401():
    session = FakeSession(FakeResponse(401))
    validator = TokenValidator(http_session=session)

    assert validator.validate("bad-token") is None


def test_validate_returns_none_for_empty_token():
    validator = TokenValidator(http_session=FakeSession(FakeResponse(200)))

    assert validator.validate("") is None


def test_validate_normalizes_missing_scopes_field():
    session = FakeSession(FakeResponse(200, {"user_id": "1", "client_id": "cid"}))
    validator = TokenValidator(http_session=session)

    result = validator.validate("tok")

    assert result["scopes"] == []
