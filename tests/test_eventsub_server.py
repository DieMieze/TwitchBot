import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import hashlib
import hmac
import json
import time

try:
    from flask import Flask  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

import pytest

pytestmark = pytest.mark.skipif(not HAS_FLASK, reason="Flask not installed")

if HAS_FLASK:
    from twitchbot_runtime.eventsub.server import create_webhook_app


SECRET = "supersecret"


def _sign(message_id, timestamp, body):
    msg = f"{message_id}{timestamp}{body}".encode()
    return "sha256=" + hmac.new(SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()


class FakeBot:
    def __init__(self):
        self.events = []

    def handle_event(self, event_name, payload=None):
        self.events.append((event_name, payload))


@pytest.fixture()
def client():
    bot = FakeBot()
    app = create_webhook_app(bot, SECRET)
    return bot, app.test_client()


def test_challenge_verification_returns_challenge(client):
    bot, c = client
    timestamp = str(int(time.time()))
    challenge = "verify-challenge-123"
    body = json.dumps({"challenge": challenge, "subscription": {"type": "channel.follow"}})

    resp = c.post(
        "/eventsub",
        data=body,
        headers={
            "Twitch-Eventsub-Message-Id": "id-1",
            "Twitch-Eventsub-Message-Timestamp": timestamp,
            "Twitch-Eventsub-Message-Type": "webhook_callback_verification",
            "Twitch-Eventsub-Message-Signature": _sign("id-1", timestamp, body),
            "Content-Type": "application/json",
        },
    )

    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == challenge


def test_notification_dispatches_to_bot(client):
    bot, c = client
    timestamp = str(int(time.time()))
    body = json.dumps(
        {
            "subscription": {"type": "channel.follow"},
            "event": {"user_name": "newfollower"},
        }
    )

    resp = c.post(
        "/eventsub",
        data=body,
        headers={
            "Twitch-Eventsub-Message-Id": "id-2",
            "Twitch-Eventsub-Message-Timestamp": timestamp,
            "Twitch-Eventsub-Message-Type": "notification",
            "Twitch-Eventsub-Message-Signature": _sign("id-2", timestamp, body),
            "Content-Type": "application/json",
        },
    )

    assert resp.status_code == 202
    assert bot.events == [("event.follow", {"username": "newfollower"})]


def test_invalid_signature_rejected(client):
    _, c = client
    timestamp = str(int(time.time()))
    body = json.dumps({"subscription": {"type": "channel.follow"}, "event": {}})

    resp = c.post(
        "/eventsub",
        data=body,
        headers={
            "Twitch-Eventsub-Message-Id": "id-3",
            "Twitch-Eventsub-Message-Timestamp": timestamp,
            "Twitch-Eventsub-Message-Type": "notification",
            "Twitch-Eventsub-Message-Signature": "sha256=deadbeef",
            "Content-Type": "application/json",
        },
    )

    assert resp.status_code == 403


def test_health_endpoint(client):
    _, c = client
    resp = c.get("/health")
    assert resp.status_code == 200
