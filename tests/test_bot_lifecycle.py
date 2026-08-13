import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.bot import TwitchBot


class FakeScheduler:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def _silently_start_then_stop(bot):
    def stopper():
        time.sleep(0.1)
        bot.request_stop()

    threading.Thread(target=stopper, daemon=True).start()


def test_run_silent_starts_and_stops_services(monkeypatch):
    Path(__file__).resolve().parent.parent / "settings.json"
    fake_scheduler = FakeScheduler()

    def fake_timer_scheduler_cls(bot):
        return fake_scheduler

    monkeypatch.setattr(
        "twitchbot_runtime.scheduler.TimerScheduler", fake_timer_scheduler_cls
    )
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._start_webhook",
        lambda self, block=False: None,
    )
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._start_eventsub",
        lambda self: None,
    )
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._stop_webhook",
        lambda self: None,
    )

    bot = TwitchBot(settings_path=None, execution_mode="silent")

    _silently_start_then_stop(bot)
    bot.run()

    assert fake_scheduler.started is True
    assert fake_scheduler.stopped is True


def test_run_test_mode_raises():
    bot = TwitchBot(settings_path=None, execution_mode="test")

    try:
        bot.run()
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def test_start_test_mode_does_not_start_scheduler(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(
        "twitchbot_runtime.scheduler.TimerScheduler",
        lambda bot: fake_scheduler,
    )
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._start_eventsub",
        lambda self: None,
    )

    bot = TwitchBot(settings_path=None, execution_mode="test")

    result = bot.start()

    assert result["status"] == "started"
    assert fake_scheduler.started is False


def test_start_silent_starts_scheduler_and_eventsub(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(
        "twitchbot_runtime.scheduler.TimerScheduler",
        lambda bot: fake_scheduler,
    )

    calls = {"eventsub": False, "webhook": False}
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._start_webhook",
        lambda self, block=False: calls.__setitem__("webhook", True),
    )
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._start_eventsub",
        lambda self: calls.__setitem__("eventsub", True),
    )
    monkeypatch.setattr(
        "twitchbot_runtime.bot.TwitchBot._stop_webhook",
        lambda self: None,
    )

    bot = TwitchBot(settings_path=None, execution_mode="silent")
    bot.start()

    assert fake_scheduler.started is True
    assert calls["eventsub"] is True
    bot.stop()
    assert fake_scheduler.stopped is True


def test_silent_mode_collects_chat_reply_instead_of_sending(tmp_path):
    bot = TwitchBot(settings_path=None, execution_mode="silent")
    bot.settings["triggers"] = [
        {
            "name": "hi",
            "when": {
                "kind": "and",
                "children": [
                    {"kind": "leaf", "condition": {"type": "command", "command": "!hi"}}
                ],
            },
            "reactions": {
                "kind": "seq",
                "children": [
                    {"kind": "reaction", "reaction": {"type": "chat_reply", "message": "hello"}},
                    {"kind": "reaction", "reaction": {"type": "clip"}},
                ],
            },
        }
    ]
    bot.trigger_resolver.triggers = bot.settings["triggers"]

    actions = bot.handle_event("chat.message", {"message": "!hi", "channel": "#test"})

    assert any(a["type"] == "chat_reply" for a in actions)
    assert any("chat" in str(s) for s in bot.sent)
    assert any("clip" in str(s) for s in bot.sent)


def test_production_mode_attempts_send_chat():
    sent = []
    bot = TwitchBot(
        settings_path=None,
        execution_mode="production",
        handlers={"send_chat": lambda channel, message: sent.append((channel, message))},
    )
    bot.settings["triggers"] = [
        {
            "name": "hi",
            "when": {
                "kind": "and",
                "children": [
                    {"kind": "leaf", "condition": {"type": "command", "command": "!hi"}}
                ],
            },
            "reactions": {
                "kind": "seq",
                "children": [
                    {"kind": "reaction", "reaction": {"type": "chat_reply", "message": "hello"}}
                ],
            },
        }
    ]
    bot.trigger_resolver.triggers = bot.settings["triggers"]

    bot.handle_event("chat.message", {"message": "!hi", "channel": "#test"})

    assert sent == [("#test", "hello")]


def test_new_chatter_inactivity_window_uses_previous_message_time():
    bot = TwitchBot(settings_path=None, execution_mode="test")
    bot.settings["triggers"] = [
        {
            "name": "welcome_back",
            "when": {
                "kind": "and",
                "children": [
                    {"kind": "leaf", "condition": {"type": "new_chatter", "time": 60}}
                ]
            },
            "reactions": {
                "kind": "seq",
                "children": [
                    {"kind": "reaction", "reaction": {"type": "chat_reply", "message": "wb {username}"}}
                ]
            },
        }
    ]

    clock = [1000.0]
    bot.trigger_resolver._time_provider = lambda: clock[0]
    bot.reaction_engine._time_provider = lambda: clock[0]

    def first_message():
        # Bob's first message: never seen before -> should fire.
        results = bot.handle_event("chat.message", {"message": "hi", "channel": "#c", "username": "Bob"})
        assert any(a.get("type") == "chat_reply" for a in results)

    def second_message_within_window():
        clock[0] += 10
        # Bob spoke 10s ago (recorded after the previous handle_event).
        # Window is 60s -> he is NOT new -> should NOT fire.
        results = bot.handle_event("chat.message", {"message": "hi", "channel": "#c", "username": "Bob"})
        assert not any(a.get("type") == "chat_reply" for a in results)

    def third_message_after_window():
        clock[0] += 60
        # Now 70s since Bob's last message -> past the 60s window -> should fire.
        results = bot.handle_event("chat.message", {"message": "hi", "channel": "#c", "username": "Bob"})
        assert any(a.get("type") == "chat_reply" for a in results)

    first_message()
    second_message_within_window()
    third_message_after_window()
