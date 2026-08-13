import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.tunnel import TunnelManager


class FakeProcess:
    def __init__(self, lines, return_code=None):
        self._lines = list(lines)
        self._return_code = return_code
        self._terminated = False
        self._killed = False
        self.poll_count = 0

        class _Stdout:
            def __init__(self, outer):
                self._outer = outer

            def readline(self):
                if self._outer._lines:
                    return self._outer._lines.pop(0)
                return ""

        self.stdout = _Stdout(self)

    def poll(self):
        self.poll_count += 1
        if not self._lines:
            return self._return_code
        return None

    def terminate(self):
        self._terminated = True

    def wait(self, timeout=None):
        return self._return_code if self._return_code is not None else 0

    def kill(self):
        self._killed = True


def test_start_parses_trycloudflare_url(monkeypatch):
    fake = FakeProcess([
        "some log line\n",
        "2024-01-01 INF |  https://abc-def.trycloudflare.com   |\n",
        "another line\n",
    ])
    manager = TunnelManager()

    def fake_popen(cmd, **kwargs):
        return fake

    monkeypatch.setattr("twitchbot_runtime.tunnel.subprocess.Popen", fake_popen)

    url = manager.start(local_port=5002, timeout=2.0)

    assert url == "https://abc-def.trycloudflare.com"
    assert manager.public_url == url


def test_start_returns_cached_url_on_second_call(monkeypatch):
    fake = FakeProcess(["https://cached.trycloudflare.com\n"])
    manager = TunnelManager()

    def fake_popen(cmd, **kwargs):
        return fake

    monkeypatch.setattr("twitchbot_runtime.tunnel.subprocess.Popen", fake_popen)

    first = manager.start(timeout=2.0)
    second = manager.start(timeout=2.0)

    assert first == "https://cached.trycloudflare.com"
    assert second == first


def test_start_raises_when_no_url_within_timeout(monkeypatch):
    fake = FakeProcess([], return_code=1)
    manager = TunnelManager()

    def fake_popen(cmd, **kwargs):
        return fake

    monkeypatch.setattr("twitchbot_runtime.tunnel.subprocess.Popen", fake_popen)

    try:
        manager.start(timeout=0.1)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass

    assert manager.public_url == ""


def test_stop_terminates_process(monkeypatch):
    fake = FakeProcess(["https://stop-test.trycloudflare.com\n"])
    manager = TunnelManager()

    monkeypatch.setattr("twitchbot_runtime.tunnel.subprocess.Popen", lambda cmd, **kw: fake)
    manager.start(timeout=2.0)
    manager.stop()

    assert fake._terminated is True
    assert manager.public_url == ""


def test_stop_without_started_process_is_noop():
    manager = TunnelManager()

    manager.stop()

    assert manager.public_url == ""
