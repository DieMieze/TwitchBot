import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "get_all_scopes", str(ROOT / "scripts" / "get_all_scopes.py")
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
get_all_scopes = _MODULE

from twitchbot_runtime.eventsub.oauth_flow import BOT_SCOPES, CHANNEL_SCOPES


class FakeFlow:
    def __init__(self):
        self.calls = []

    def start_and_wait(self, client_id, scopes, redirect_uri, port=5003, client_secret=""):
        self.calls.append({
            "client_id": client_id,
            "scopes": list(scopes),
            "redirect_uri": redirect_uri,
            "port": port,
            "client_secret": client_secret,
        })
        return ("access-" + client_id, "refresh-" + client_id)


def _patch_flow(monkeypatch, flow):
    monkeypatch.setattr(get_all_scopes, "OAuthFlowStarter", lambda: flow)


def _patch_oauth_port(monkeypatch, port=5003, redirect_uri=None):
    """Patch _resolve_oauth_port so tests don't touch settings.json/sockets."""
    uri = redirect_uri or f"http://localhost:{port}/oauth/callback"
    monkeypatch.setattr(get_all_scopes, "_resolve_oauth_port", lambda: (port, uri))


def _write_env(tmp_path, mapping):
    env_path = tmp_path / ".env"
    lines = [f"{k}={v}" for k, v in mapping.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def test_main_writes_bot_and_channel_tokens(tmp_path, monkeypatch):
    env_path = _write_env(tmp_path, {"BOT_CLIENT_ID": "bot-cid", "CHANNEL_CLIENT_ID": "chan-cid"})
    flow = FakeFlow()
    _patch_flow(monkeypatch, flow)
    _patch_oauth_port(monkeypatch, port=5010)

    rc = get_all_scopes.main(["--env-path", str(env_path)])

    assert rc == 0
    assert len(flow.calls) == 2
    assert flow.calls[0]["client_id"] == "bot-cid"
    assert flow.calls[0]["scopes"] == BOT_SCOPES
    assert flow.calls[0]["port"] == 5010
    assert flow.calls[0]["redirect_uri"] == "http://localhost:5010/oauth/callback"
    assert flow.calls[1]["client_id"] == "chan-cid"
    assert flow.calls[1]["scopes"] == CHANNEL_SCOPES
    assert flow.calls[1]["port"] == 5010
    from twitchbot_runtime.twitch_settings import TwitchSettings

    settings = TwitchSettings.load(env_path)
    assert settings.bot_oauth_token == "access-bot-cid"
    assert settings.bot_refresh_token == "refresh-bot-cid"
    assert settings.channel_oauth_token == "access-chan-cid"


def test_main_bot_only_skips_channel(tmp_path, monkeypatch):
    env_path = _write_env(tmp_path, {"BOT_CLIENT_ID": "bot-cid"})
    flow = FakeFlow()
    _patch_flow(monkeypatch, flow)
    _patch_oauth_port(monkeypatch)

    rc = get_all_scopes.main(["--env-path", str(env_path), "--bot-only"])

    assert rc == 0
    assert len(flow.calls) == 1
    assert flow.calls[0]["scopes"] == BOT_SCOPES


def test_main_channel_only_skips_bot(tmp_path, monkeypatch):
    env_path = _write_env(tmp_path, {"BOT_CLIENT_ID": "bot-cid"})
    flow = FakeFlow()
    _patch_flow(monkeypatch, flow)
    _patch_oauth_port(monkeypatch)

    rc = get_all_scopes.main(["--env-path", str(env_path), "--channel-only"])

    assert rc == 0
    assert len(flow.calls) == 1
    assert flow.calls[0]["scopes"] == CHANNEL_SCOPES


def test_main_returns_error_when_client_id_missing(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    flow = FakeFlow()
    _patch_flow(monkeypatch, flow)
    _patch_oauth_port(monkeypatch)

    rc = get_all_scopes.main(["--env-path", str(env_path)])

    assert rc == 2
    assert flow.calls == []


def test_main_falls_back_channel_client_id_to_bot(tmp_path, monkeypatch):
    env_path = _write_env(tmp_path, {"BOT_CLIENT_ID": "shared-cid"})
    flow = FakeFlow()
    _patch_flow(monkeypatch, flow)
    _patch_oauth_port(monkeypatch)

    get_all_scopes.main(["--env-path", str(env_path)])

    assert flow.calls[1]["client_id"] == "shared-cid"


def test_main_returns_nonzero_when_flow_returns_none(tmp_path, monkeypatch):
    env_path = _write_env(tmp_path, {"BOT_CLIENT_ID": "bot-cid"})

    class NoneFlow:
        def start_and_wait(self, client_id, scopes, redirect_uri, port=5003, client_secret=""):
            return None

    monkeypatch.setattr(get_all_scopes, "OAuthFlowStarter", lambda: NoneFlow())
    _patch_oauth_port(monkeypatch)

    rc = get_all_scopes.main(["--env-path", str(env_path), "--bot-only"])

    assert rc == 1


def test_main_passes_bot_client_secret_to_flow(tmp_path, monkeypatch):
    env_path = _write_env(tmp_path, {"BOT_CLIENT_ID": "bot-cid", "BOT_CLIENT_SECRET": "topsecret"})
    flow = FakeFlow()
    _patch_flow(monkeypatch, flow)
    _patch_oauth_port(monkeypatch)

    get_all_scopes.main(["--env-path", str(env_path), "--bot-only"])

    assert flow.calls[0]["client_secret"] == "topsecret"


def test_main_passes_empty_secret_when_unset(tmp_path, monkeypatch):
    env_path = _write_env(tmp_path, {"BOT_CLIENT_ID": "bot-cid"})
    flow = FakeFlow()
    _patch_flow(monkeypatch, flow)
    _patch_oauth_port(monkeypatch)

    get_all_scopes.main(["--env-path", str(env_path), "--bot-only"])

    assert flow.calls[0]["client_secret"] == ""


def test_resolve_oauth_port_builds_redirect_uri_and_warns_when_non_default(monkeypatch, tmp_path, capsys):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"runtime": {"oauth": {"port": 5010}}}', encoding="utf-8")
    monkeypatch.setattr(get_all_scopes, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(get_all_scopes, "resolve_port_or_exit", lambda *a, **k: 5010)

    port, redirect_uri = get_all_scopes._resolve_oauth_port()

    assert port == 5010
    assert redirect_uri == "http://localhost:5010/oauth/callback"
    captured = capsys.readouterr()
    assert "5010" in captured.err
    assert "Redirect URI" in captured.err or "Twitch Developer Console" in captured.err


def test_resolve_oauth_port_no_warning_for_default(monkeypatch, tmp_path, capsys):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"runtime": {"oauth": {"port": 5003}}}', encoding="utf-8")
    monkeypatch.setattr(get_all_scopes, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(get_all_scopes, "resolve_port_or_exit", lambda *a, **k: 5003)

    port, redirect_uri = get_all_scopes._resolve_oauth_port()

    assert port == 5003
    assert redirect_uri == "http://localhost:5003/oauth/callback"
    captured = capsys.readouterr()
    assert captured.err == ""
