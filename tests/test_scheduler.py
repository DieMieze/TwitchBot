import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.scheduler import TimerScheduler


class FakeBot:
    def __init__(self, triggers=None):
        self.settings = {"triggers": triggers or []}
        self.events = []
        self._lock = threading.Lock()

    def handle_event(self, event_name, payload=None):
        with self._lock:
            self.events.append(event_name)


def test_compute_interval_uses_min_time_condition():
    bot = FakeBot(
        triggers=[
            {
                "name": "t",
                "when": {
                    "kind": "and",
                    "children": [
                        {"kind": "leaf", "condition": {"type": "time", "interval_minutes": 0.05}}
                    ],
                },
            }
        ]
    )
    scheduler = TimerScheduler(bot)

    interval = scheduler.compute_interval()

    assert interval == max(0.05 * 60, TimerScheduler.MIN_INTERVAL_SECONDS)


def test_compute_interval_defaults_when_no_time_triggers():
    bot = FakeBot(triggers=[])
    scheduler = TimerScheduler(bot)

    assert scheduler.compute_interval() == TimerScheduler.DEFAULT_INTERVAL_SECONDS


def test_scheduler_dispatches_timer_tick():
    bot = FakeBot()
    scheduler = TimerScheduler(bot, interval_seconds=0.05)
    scheduler.start()

    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and not bot.events:
            time.sleep(0.02)
    finally:
        scheduler.stop()

    assert "timer.tick" in bot.events


def test_scheduler_stop_terminates_loop():
    bot = FakeBot()
    scheduler = TimerScheduler(bot, interval_seconds=0.05)
    scheduler.start()
    time.sleep(0.1)
    scheduler.stop()

    assert scheduler._thread is None or not scheduler._thread.is_alive()
