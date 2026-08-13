import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import time

from twitchbot_runtime.eventsub.events import normalize_event
from twitchbot_runtime.eventsub.verify import (
    extract_challenge,
    is_challenge_request,
    verify_signature,
)

SECRET = "supersecret"


def _signature(message_id, message_timestamp, body):
    import hashlib
    import hmac

    msg = f"{message_id}{message_timestamp}{body}".encode()
    return "sha256=" + hmac.new(SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def test_verify_signature_accepts_valid_request():
    message_id = "abc-123"
    timestamp = str(int(time.time()))
    body = '{"event": {}}'

    assert verify_signature(
        message_id,
        timestamp,
        body,
        SECRET,
        _signature(message_id, timestamp, body),
        now=float(timestamp),
    ) is True


def test_verify_signature_rejects_invalid_signature():
    assert verify_signature(
        "id",
        str(int(time.time())),
        "body",
        SECRET,
        "sha256=deadbeef",
        now=time.time(),
    ) is False


def test_verify_signature_rejects_stale_timestamp():
    message_id = "abc-123"
    old_timestamp = str(int(time.time()) - 3600)
    body = '{"event": {}}'

    assert verify_signature(
        message_id,
        old_timestamp,
        body,
        SECRET,
        _signature(message_id, old_timestamp, body),
        now=time.time(),
    ) is False


def test_verify_signature_rejects_missing_secret():
    assert verify_signature("id", "0", "body", "", "sha256=x") is False


def test_is_challenge_request_detects_verification():
    headers = {"Twitch-Eventsub-Message-Type": "webhook_callback_verification"}
    assert is_challenge_request(headers, {}) is True


def test_is_challenge_request_ignores_notification():
    headers = {"Twitch-Eventsub-Message-Type": "notification"}
    assert is_challenge_request(headers, {}) is False


def test_extract_challenge_returns_challenge():
    assert extract_challenge({"challenge": "verify-me"}) == "verify-me"


def test_extract_challenge_returns_none_when_missing():
    assert extract_challenge({"foo": "bar"}) is None


def test_normalize_chat_message_event():
    event = {
        "broadcaster_user_login": "streamer",
        "chatter_user_name": "viewer",
        "message": {"text": "!hello world"},
    }

    name, payload = normalize_event("channel.chat.message", event)

    assert name == "chat.message"
    assert payload["message"] == "!hello world"
    assert payload["username"] == "viewer"
    assert payload["channel"] == "streamer"
    assert payload["reward_id"] == ""
    assert payload["is_new_chatter"] is False


def test_normalize_follow_event():
    name, payload = normalize_event("channel.follow", {"user_name": "newfollower"})

    assert name == "event.follow"
    assert payload["username"] == "newfollower"


def test_normalize_cheer_event():
    name, payload = normalize_event("channel.cheer", {"user_name": "cheerleader", "bits": 500})

    assert name == "event.cheer"
    assert payload["username"] == "cheerleader"
    assert payload["bits"] == 500


def test_normalize_redemption_event():
    event = {"user_name": "redeemer", "reward": {"id": "reward-1"}}
    name, payload = normalize_event(
        "channel.channel_points_custom_reward_redemption.add", event
    )

    assert name == "channel_points.redemption"
    assert payload["reward_id"] == "reward-1"
    assert payload["username"] == "redeemer"


def test_normalize_subscribe_event_defaults_gif_id():
    name, payload = normalize_event("channel.subscribe", {"user_name": "subber"})

    assert name == "event.sub"
    assert payload["gif_id"] == "sub"
