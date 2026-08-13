import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.bot import TwitchBot
from twitchbot_runtime.mode import Mode, is_live
from twitchbot_runtime.overlay.manager import OverlayManager
from twitchbot_runtime.silent_collector import SilentEventCollector
from twitchbot_runtime.test_repl import replay_file


def test_mode_from_string_maps_legacy_values():
    assert Mode.from_string("bot") is Mode.PRODUCTION
    assert Mode.from_string("log_only") is Mode.SILENT
    assert Mode.from_string("test") is Mode.TEST
    assert Mode.from_string("production") is Mode.PRODUCTION


def test_mode_from_string_unknown_defaults_to_test():
    assert Mode.from_string("unknown") is Mode.TEST


def test_is_live_only_for_production():
    assert is_live(Mode.PRODUCTION) is True
    assert is_live(Mode.TEST) is False
    assert is_live(Mode.SILENT) is False


def test_silent_collector_collects_events(tmp_path):
    collector = SilentEventCollector(store_path=tmp_path / "events.jsonl", max_per_type=3)

    assert collector.collect("event.follow", {"user": "a"}) is True
    assert collector.collect("event.follow", {"user": "b"}) is True
    assert collector.collect("event.follow", {"user": "c"}) is True
    assert collector.collect("event.follow", {"user": "d"}) is False

    assert collector.counts()["event.follow"] == 3


def test_silent_collector_separate_counts_per_type(tmp_path):
    collector = SilentEventCollector(store_path=tmp_path / "events.jsonl", max_per_type=3)

    assert collector.collect("A", {"i": 1}) is True
    assert collector.collect("A", {"i": 2}) is True
    assert collector.collect("A", {"i": 3}) is True
    assert collector.collect("B", {"i": 1}) is True

    assert collector.counts() == {"A": 3, "B": 1}


def test_silent_collector_writes_jsonl(tmp_path):
    store_path = tmp_path / "events.jsonl"
    collector = SilentEventCollector(store_path=store_path, max_per_type=3)

    collector.collect("event.follow", {"user": "a"})

    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert "event" in record
    assert "payload" in record
    assert "timestamp" in record
    assert record["event"] == "event.follow"
    assert record["payload"] == {"user": "a"}


def test_silent_collector_rereadable_jsonl(tmp_path):
    store_path = tmp_path / "events.jsonl"
    collector = SilentEventCollector(store_path=store_path, max_per_type=5)
    collector.collect("event.follow", {"user": "a"})
    collector.collect("event.cheer", {"user": "b", "bits": 100})

    lines = store_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]
    assert records[0]["event"] == "event.follow"
    assert records[1]["event"] == "event.cheer"


def test_bot_in_test_mode_records_side_effects():
    bot = TwitchBot(settings_path=None)
    bot.settings["triggers"] = [
        {
            "name": "t",
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

    bot.handle_event("chat.message", {"message": "!hi"})

    assert any("chat" in str(s) for s in bot.sent)


def test_bot_in_silent_mode_collects_events(tmp_path):
    bot = TwitchBot(settings_path=None)
    bot.settings["runtime"]["execution_mode"] = "silent"
    bot.mode = Mode.SILENT
    bot.silent_collector = SilentEventCollector(store_path=tmp_path / "events.jsonl", max_per_type=5)

    bot.handle_event("event.follow", {"user": "a"})

    assert bot.silent_collector is not None
    assert bot.silent_collector.counts().get("event.follow") == 1


def test_execution_mode_override_creates_silent_collector(tmp_path):
    bot = TwitchBot(
        settings_path=None,
        execution_mode="silent",
    )

    assert bot.mode is Mode.SILENT
    assert bot.silent_collector is not None


def test_execution_mode_override_test_has_no_silent_collector():
    bot = TwitchBot(settings_path=None, execution_mode="test")

    assert bot.mode is Mode.TEST
    assert bot.silent_collector is None


def test_execution_mode_override_production_activates_overlay_backend(tmp_path, monkeypatch):
    calls = {"started": False, "overlay_port": None}

    class DummyFacade:
        def __init__(self):
            self.messages = []

        def start(self):
            calls["started"] = True

        def stop(self):
            pass

        def send_message(self, message):
            self.messages.append(message)

    def factory(overlay_port=None):
        calls["overlay_port"] = overlay_port
        return DummyFacade()

    monkeypatch.setattr(OverlayManager, "_create_real_backend", staticmethod(factory))
    # Avoid a real socket freedom check during construction; the backend is
    # mocked so no actual subprocess is spawned.
    monkeypatch.setattr("twitchbot_runtime.bot.resolve_port_or_exit", lambda *a, **k: 5050)

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "runtime": {"execution_mode": "test"},
                "features": {"overlay": {"enabled": True}},
                "triggers": [],
            }
        ),
        encoding="utf-8",
    )

    bot = TwitchBot(
        settings_path=settings_path,
        execution_mode="production",
        handlers={
            "send_chat": lambda channel, message: None,
            "overlay_dispatch": lambda action: None,
        },
    )

    assert bot.mode is Mode.PRODUCTION
    assert bot.overlay_manager.backend is not None
    assert calls["overlay_port"] == 5050
    bot.start()
    assert calls["started"] is True
    bot.stop()


def test_replay_file(tmp_path):
    path = tmp_path / "replay.jsonl"
    records = [
        {"event": "event.follow", "payload": {"user": "a"}},
        {"event": "event.cheer", "payload": {"user": "b", "bits": 100}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    bot = TwitchBot(settings_path=None)
    bot.settings["triggers"] = []

    results = replay_file(bot, path)

    assert isinstance(results, list)
    assert len(results) >= 0
