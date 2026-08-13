import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from twitchbot_runtime.overlay.facade import OverlayFacade


class FakeProcess:
    instances = []

    def __init__(self, target=None, args=()):
        self.target = target
        self.args = args
        self.alive = False
        self.joined = False
        self.join_calls = []
        self.terminated = False
        FakeProcess.instances.append(self)

    def start(self):
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        self.alive = False
        self.joined = True

    def terminate(self):
        self.terminated = True
        self.alive = False


class BlockingFakeProcess(FakeProcess):
    """Simuliert ein join(), das den Timeout überschreitet (Prozess hängt)."""

    def __init__(self, target=None, args=(), hang_seconds=10):
        super().__init__(target=target, args=args)
        import threading
        self._hang_seconds = hang_seconds
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self.alive = True
        import threading
        self._thread = threading.Thread(target=self._stay_alive, daemon=True)
        self._thread.start()

    def _stay_alive(self):
        self._stop.wait(self._hang_seconds)

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        if timeout is None:
            self._stop.set()
            if self._thread is not None:
                self._thread.join()
            self.alive = False
            self.joined = True
            return
        # Wartet maximal timeout; wenn das Stop-Event nicht gesetzt ist,
        # bleibt der Prozess "am Leben" (Timeout überschritten).
        signaled = self._stop.wait(timeout)
        if signaled or self.terminated:
            self.alive = False
            self.joined = True
            if self._thread is not None:
                self._thread.join()
        else:
            self.alive = True
            self.joined = False

    def terminate(self):
        self.terminated = True
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.alive = False
        self.joined = True


def test_start_spawns_process_and_sets_running_event(monkeypatch):
    FakeProcess.instances = []
    monkeypatch.setattr("twitchbot_runtime.overlay.facade.Process", FakeProcess)

    facade = OverlayFacade()

    assert not facade.running_event.is_set()

    facade.start()

    assert facade.running_event.is_set()
    assert len(FakeProcess.instances) == 1
    assert FakeProcess.instances[0].alive is True


def test_start_is_idempotent_when_process_alive(monkeypatch):
    FakeProcess.instances = []
    monkeypatch.setattr("twitchbot_runtime.overlay.facade.Process", FakeProcess)

    facade = OverlayFacade()
    facade.start()
    facade.start()

    assert len(FakeProcess.instances) == 1


def test_send_message_enqueues_when_process_alive(monkeypatch):
    FakeProcess.instances = []
    monkeypatch.setattr("twitchbot_runtime.overlay.facade.Process", FakeProcess)

    facade = OverlayFacade()
    facade.start()

    facade.send_message({"action": "overlay_text", "data": {"text": "Hi"}})

    assert facade.queue.get(timeout=1) == {"action": "overlay_text", "data": {"text": "Hi"}}


def test_send_message_noop_when_no_process():
    facade = OverlayFacade()

    facade.send_message({"action": "overlay_text"})

    assert facade.queue.empty()


def test_stop_joins_process_and_sends_stop_message(monkeypatch):
    FakeProcess.instances = []
    monkeypatch.setattr("twitchbot_runtime.overlay.facade.Process", FakeProcess)

    facade = OverlayFacade()
    facade.start()
    process = FakeProcess.instances[0]

    facade.stop()

    assert not process.alive
    assert not facade.running_event.is_set()
    assert facade.queue.get(timeout=1) == "STOP"
    assert process.join_calls == [facade._JOIN_TIMEOUT_SECONDS]


def test_stop_clears_running_event_before_join(monkeypatch):
    FakeProcess.instances = []
    monkeypatch.setattr("twitchbot_runtime.overlay.facade.Process", FakeProcess)

    facade = OverlayFacade()
    facade.start()

    # Passe join so an, dass es den Status von running_event *während* join
    # festhält — die clear() muss bereits vor dem join passiert sein.
    captured = {"during_join": None}
    original_join = FakeProcess.join

    def spy_join(self, timeout=None):
        captured["during_join"] = facade.running_event.is_set()
        return original_join(self, timeout)

    monkeypatch.setattr(FakeProcess, "join", spy_join)

    facade.stop()

    assert captured["during_join"] is False, "running_event muss vor join() gelöscht sein"
    assert facade.queue.get(timeout=1) == "STOP"


def test_stop_terminates_after_timeout(monkeypatch):
    FakeProcess.instances = []
    monkeypatch.setattr("twitchbot_runtime.overlay.facade.Process", BlockingFakeProcess)
    monkeypatch.setattr(OverlayFacade, "_JOIN_TIMEOUT_SECONDS", 0.2)

    facade = OverlayFacade()
    facade.start()
    process = FakeProcess.instances[0]
    assert isinstance(process, BlockingFakeProcess)

    facade.stop()

    assert process.terminated, "terminate() muss nach Timeout greifen"
    assert process.alive is False
    assert not facade.running_event.is_set()
    assert facade.queue.get(timeout=1) == "STOP"
    # Erster join mit Timeout, zweiter join nach terminate (ebenfalls mit Timeout).
    assert process.join_calls[0] == 0.2
    assert len(process.join_calls) == 2
