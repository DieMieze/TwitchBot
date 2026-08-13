import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import json

import pytest

from twitchbot_runtime.ports import (
    DEFAULT_PORTS,
    PortInUseError,
    find_free_alternatives,
    get_effective_ports,
    get_port,
    is_port_free,
    resolve_port_or_exit,
)


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _busy_port() -> int:
    import socket

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    return server, server.getsockname()[1]


def test_default_ports_match_historic_values():
    assert DEFAULT_PORTS == {
        "overlay": 5000,
        "webui": 5001,
        "webhook": 5002,
        "pos_ui": 5003,
        "oauth": 5003,
    }


def test_is_port_free_returns_true_for_unused_port():
    port = _free_port()
    assert is_port_free("127.0.0.1", port) is True


def test_is_port_free_returns_false_for_bound_port():
    server, port = _busy_port()
    try:
        assert is_port_free("127.0.0.1", port) is False
    finally:
        server.close()


def test_find_free_alternatives_returns_free_ports_excluding_input():
    free = _free_port()
    result = find_free_alternatives("127.0.0.1", free, count=3)
    assert len(result) == 3
    assert free not in result
    for p in result:
        assert is_port_free("127.0.0.1", p)


def test_find_free_alternatives_skips_busy_ports():
    server, busy = _busy_port()
    try:
        result = find_free_alternatives("127.0.0.1", busy, count=2)
        assert busy not in result
        assert len(result) == 2
    finally:
        server.close()


def test_get_port_uses_persisted_value_without_prompt(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"runtime": {"overlay": {"port": 1234}}}),
        encoding="utf-8",
    )

    def fail_prompt(*a, **k):
        raise AssertionError("must not prompt when value persisted")

    monkeypatch.setattr("twitchbot_runtime.ports._prompt_port", fail_prompt)
    monkeypatch.setattr("twitchbot_runtime.ports._is_interactive", lambda: True)

    port = get_port("overlay", settings_path=settings_path)
    assert port == 1234


def test_get_port_non_interactive_uses_default_without_persisting(tmp_path, monkeypatch, caplog):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"runtime": {}}), encoding="utf-8")

    monkeypatch.setattr("twitchbot_runtime.ports._is_interactive", lambda: False)

    port = get_port("overlay", settings_path=settings_path)
    assert port == DEFAULT_PORTS["overlay"]

    # Default must NOT be persisted on non-interactive runs.
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "overlay" not in saved.get("runtime", {})


def test_get_port_interactive_prompts_and_persists(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"runtime": {}}), encoding="utf-8")

    monkeypatch.setattr("twitchbot_runtime.ports._is_interactive", lambda: True)
    monkeypatch.setattr("twitchbot_runtime.ports._prompt_port", lambda c, d: 4242)

    port = get_port("overlay", settings_path=settings_path)
    assert port == 4242

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["runtime"]["overlay"]["port"] == 4242


def test_get_port_interactive_empty_input_keeps_default(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"runtime": {}}), encoding="utf-8")

    monkeypatch.setattr("twitchbot_runtime.ports._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")

    port = get_port("overlay", settings_path=settings_path)
    assert port == DEFAULT_PORTS["overlay"]


def test_get_port_rejects_unknown_component():
    with pytest.raises(ValueError):
        get_port("nope")


def test_get_port_raises_port_in_use_when_occupied(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"runtime": {"overlay": {"port": 0}}}),
        encoding="utf-8",
    )
    server, busy = _busy_port()
    try:
        settings_path.write_text(
            json.dumps({"runtime": {"overlay": {"port": busy}}}),
            encoding="utf-8",
        )
        with pytest.raises(PortInUseError) as exc_info:
            get_port("overlay", settings_path=settings_path)
        assert exc_info.value.port == busy
        assert len(exc_info.value.alternatives) >= 1
        assert busy not in exc_info.value.alternatives
    finally:
        server.close()


def test_get_port_rejects_invalid_persisted_value(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"runtime": {"overlay": {"port": 70000}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("twitchbot_runtime.ports._is_interactive", lambda: False)
    # Invalid persisted value is treated as missing → default (non-interactive).
    port = get_port("overlay", settings_path=settings_path)
    assert port == DEFAULT_PORTS["overlay"]


def test_get_port_persist_false_does_not_write(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"runtime": {}}), encoding="utf-8")

    monkeypatch.setattr("twitchbot_runtime.ports._is_interactive", lambda: True)
    monkeypatch.setattr("twitchbot_runtime.ports._prompt_port", lambda c, d: 4242)

    port = get_port("overlay", settings_path=settings_path, persist=False)
    assert port == 4242
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "overlay" not in saved.get("runtime", {})


def test_resolve_port_or_exit_returns_port_when_free(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"runtime": {"overlay": {"port": _free_port()}}}),
        encoding="utf-8",
    )
    port = resolve_port_or_exit("overlay", settings_path=settings_path)
    assert isinstance(port, int)


def test_resolve_port_or_exit_exits_when_port_in_use(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    server, busy = _busy_port()
    try:
        settings_path.write_text(
            json.dumps({"runtime": {"overlay": {"port": busy}}}),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as exc_info:
            resolve_port_or_exit("overlay", settings_path=settings_path)
        assert exc_info.value.code == 1
    finally:
        server.close()


def test_oauth_prompt_emits_twitch_warning(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("twitchbot_runtime.ports._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")

    port = get_port("oauth", settings={"runtime": {}}, settings_path=tmp_path / "settings.json")
    assert port == DEFAULT_PORTS["oauth"]
    captured = capsys.readouterr()
    assert "Twitch Developer Console" in captured.err or "Redirect URI" in captured.err


def test_get_effective_ports_returns_all_components_with_status():
    settings = {"runtime": {"overlay": {"port": 6000}, "webhook": {"port": 6001, "host": "127.0.0.1"}}}
    result = get_effective_ports(settings)
    assert set(result.keys()) == set(DEFAULT_PORTS.keys())
    assert result["overlay"]["port"] == 6000
    assert result["overlay"]["default"] == 5000
    assert isinstance(result["overlay"]["free"], bool)
    assert result["webhook"]["port"] == 6001
    # Unconfigured components fall back to defaults.
    assert result["webui"]["port"] == DEFAULT_PORTS["webui"]
    assert result["webui"]["default"] == DEFAULT_PORTS["webui"]


def test_get_effective_ports_never_prompts_or_persists(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"runtime": {}}), encoding="utf-8")

    def fail_prompt(*a, **k):
        raise AssertionError("get_effective_ports must not prompt")

    monkeypatch.setattr("twitchbot_runtime.ports._prompt_port", fail_prompt)
    result = get_effective_ports({"runtime": {}})
    assert result["pos_ui"]["port"] == DEFAULT_PORTS["pos_ui"]
    # No persistence.
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved == {"runtime": {}}


def test_persist_overwrites_existing_port(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"runtime": {"webui": {"port": 9000}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("twitchbot_runtime.ports._is_interactive", lambda: True)
    monkeypatch.setattr("twitchbot_runtime.ports._prompt_port", lambda c, d: 9001)

    # persisted value present (9000) → no prompt, no overwrite
    port = get_port("webui", settings_path=settings_path)
    assert port == 9000
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["runtime"]["webui"]["port"] == 9000
