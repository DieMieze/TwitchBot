import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import json

try:
    from flask import Flask  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

import pytest

pytestmark = pytest.mark.skipif(not HAS_FLASK, reason="Flask not installed")

if HAS_FLASK:
    from twitchbot_runtime.overlay_pos_ui import app as pos_ui_module
    from twitchbot_runtime.overlay_pos_ui.app import (
        DEFAULT_PORT,
        _resolve_gif_path,
        create_app,
    )


@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    config_path = tmp_path / "Stream_Pet.json"
    stream_pet_dir = tmp_path / "StreamPet"
    stream_pet_dir.mkdir()
    monkeypatch.setattr(pos_ui_module, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(pos_ui_module, "STREAM_PET_DIR", str(stream_pet_dir))
    return {"config_path": config_path, "stream_pet_dir": stream_pet_dir}


@pytest.fixture()
def client(isolated_config):
    return create_app().test_client()


def test_default_port_is_5003_and_does_not_collide_with_existing_ports():
    assert DEFAULT_PORT == 5003
    assert DEFAULT_PORT not in (5000, 5001, 5002)


def test_overlay_pos_ui_port_env_override(monkeypatch):
    # main() reads OVERLAY_POS_UI_PORT; verify it is honored without actually
    # binding a socket (patch app.run to capture the port).
    captured = {}

    class FakeApp:
        def run(self, host, port, debug):
            captured["host"] = host
            captured["port"] = port
            captured["debug"] = debug

    monkeypatch.setattr(pos_ui_module.os, "environ", {"OVERLAY_POS_UI_PORT": "5301"})
    monkeypatch.setattr(pos_ui_module, "create_app", lambda: FakeApp())
    assert pos_ui_module.main() == 0
    assert captured["port"] == 5301
    assert captured["host"] == "127.0.0.1"
    assert captured["debug"] is False


def test_overlay_pos_ui_main_reads_port_from_settings(monkeypatch, tmp_path):
    # Without env var, main() resolves pos_ui port from settings.json. Patch
    # resolve_port_or_exit to avoid a real socket freedom check.
    captured = {}

    class FakeApp:
        def run(self, host, port, debug):
            captured["host"] = host
            captured["port"] = port
            captured["debug"] = debug

    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(pos_ui_module, "SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(pos_ui_module.os, "environ", {})
    monkeypatch.setattr(pos_ui_module, "create_app", lambda: FakeApp())
    monkeypatch.setattr(pos_ui_module, "resolve_port_or_exit", lambda c, s, p: 5302)

    assert pos_ui_module.main() == 0
    assert captured["port"] == 5302


def test_overlay_pos_ui_main_env_override_takes_priority_over_settings(monkeypatch, tmp_path):
    # OVERLAY_POS_UI_PORT must win over settings.json (not persisted).
    captured = {}

    class FakeApp:
        def run(self, host, port, debug):
            captured["port"] = port

    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(pos_ui_module, "SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(pos_ui_module.os, "environ", {"OVERLAY_POS_UI_PORT": "5400"})
    monkeypatch.setattr(pos_ui_module, "create_app", lambda: FakeApp())

    def fail_resolve(*a, **k):
        raise AssertionError("env var must take priority; resolve must not run")

    monkeypatch.setattr(pos_ui_module, "resolve_port_or_exit", fail_resolve)
    assert pos_ui_module.main() == 0
    assert captured["port"] == 5400


def test_overlay_pos_ui_main_invalid_env_falls_back_to_default(monkeypatch, tmp_path):
    captured = {}

    class FakeApp:
        def run(self, host, port, debug):
            captured["port"] = port

    monkeypatch.setattr(pos_ui_module, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(pos_ui_module.os, "environ", {"OVERLAY_POS_UI_PORT": "notanumber"})
    monkeypatch.setattr(pos_ui_module, "create_app", lambda: FakeApp())

    assert pos_ui_module.main() == 0
    assert captured["port"] == DEFAULT_PORT


def test_overlay_link_uses_settings_overlay_port(monkeypatch, tmp_path):
    # The HTML "view in overlay" link must reflect runtime.overlay.port.
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"runtime": {"overlay": {"port": 6000}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pos_ui_module, "SETTINGS_PATH", str(settings_path))

    html = pos_ui_module._render_page_html()
    assert "http://localhost:6000/" in html
    assert "Port 6000" in html
    assert "http://localhost:5000/" not in html


def test_overlay_link_falls_back_to_default_when_no_settings(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(pos_ui_module, "SETTINGS_PATH", str(settings_path))
    assert not settings_path.exists()

    html = pos_ui_module._render_page_html()
    assert "http://localhost:5000/" in html
    assert "Port 5000" in html


def test_overlay_link_falls_back_to_default_when_port_invalid(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"runtime": {"overlay": {"port": 70000}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pos_ui_module, "SETTINGS_PATH", str(settings_path))

    html = pos_ui_module._render_page_html()
    assert "http://localhost:5000/" in html


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "StreamPet Konfiguration" in body
    assert "Speichern" in body


def test_get_config_returns_empty_when_file_missing(client, isolated_config):
    assert not isolated_config["config_path"].exists()
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {}


def test_post_then_get_roundtrip(client, isolated_config):
    payload = {
        "idle": "StreamPet/Einhorn_Idle.gif",
        "animations": {"wave": "StreamPet/Einhorn_Hi.gif"},
        "stream_pet_config": {
            "position": {"x": 0.25, "y": 0.5},
            "height": 250,
            "font": "Verdana",
            "text_size": 16,
            "speech_bubble_position": {"x": 10, "y": -20},
        },
        "speech_bubble_text": "Hello {username}",
        "speech_bubble_toggle": False,
    }
    resp = client.post("/api/config", json=payload)
    assert resp.status_code == 200

    saved = json.loads(isolated_config["config_path"].read_text(encoding="utf-8"))
    assert saved == payload

    resp = client.get("/api/config")
    assert resp.get_json() == payload


def test_post_config_rejects_non_object(client):
    resp = client.post("/api/config", json=["not", "an", "object"])
    assert resp.status_code == 400


def test_post_config_rejects_missing_body(client):
    resp = client.post("/api/config")
    assert resp.status_code == 400


def test_serve_stream_pet_rejects_traversal(client, isolated_config):
    for bad in ("../secret.txt", "..\\..\\win.ini", "../../.env", ""):
        resp = client.get(f"/StreamPet/{bad}")
        assert resp.status_code in (400, 404), bad


def test_serve_stream_pet_serves_existing_file(client, isolated_config):
    gif = isolated_config["stream_pet_dir"] / "Einhorn_Idle.gif"
    gif.write_bytes(b"GIF89a dummy")
    resp = client.get("/StreamPet/Einhorn_Idle.gif")
    assert resp.status_code == 200
    assert resp.get_data() == b"GIF89a dummy"


def test_resolve_gif_path_rejects_empty(isolated_config):
    # secure_filename neutralizes traversal to a safe basename; only an empty
    # result raises ValueError. Traversal like "../x.gif" is resolved to
    # "x.gif" inside STREAM_PET_DIR (file-not-found at the route layer, 404).
    with pytest.raises(ValueError):
        _resolve_gif_path("")


def test_resolve_gif_path_neutralizes_traversal(isolated_config):
    # Traversal segments are stripped by secure_filename; the resolved path
    # must remain inside STREAM_PET_DIR.
    resolved = _resolve_gif_path("../../etc/passwd")
    assert Path(resolved).parent == Path(isolated_config["stream_pet_dir"]).resolve()
    assert Path(resolved).name == "passwd" or Path(resolved).name == "etc_passwd"


def test_idle_gif_route_uses_config_idle_path(client, isolated_config):
    gif = isolated_config["stream_pet_dir"] / "Einhorn_Idle.gif"
    gif.write_bytes(b"GIF89a dummy")
    client.post("/api/config", json={"idle": "StreamPet/Einhorn_Idle.gif"})
    resp = client.get("/StreamPet.gif")
    assert resp.status_code == 200
    assert resp.get_data() == b"GIF89a dummy"


def test_idle_gif_route_404_when_missing(client, isolated_config):
    client.post("/api/config", json={"idle": "StreamPet/Einhorn_Idle.gif"})
    resp = client.get("/StreamPet.gif")
    assert resp.status_code == 404


def test_idle_gif_route_404_when_idle_invalid(client, isolated_config):
    # secure_filename neutralizes "../escape.gif" to "escape.gif"; file is not
    # present so the route returns 404 (still no traversal — path stays inside
    # STREAM_PET_DIR).
    client.post("/api/config", json={"idle": "../escape.gif"})
    resp = client.get("/StreamPet.gif")
    assert resp.status_code == 404


def test_api_streampet_gifs_empty_when_dir_empty(client, isolated_config):
    resp = client.get("/api/streampet/gifs")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_api_streampet_gifs_lists_gifs_sorted(client, isolated_config):
    d = isolated_config["stream_pet_dir"]
    (d / "b.gif").write_bytes(b"GIF89a")
    (d / "a.gif").write_bytes(b"GIF89a")
    (d / "notgif.txt").write_bytes(b"nope")
    resp = client.get("/api/streampet/gifs")
    assert resp.status_code == 200
    assert resp.get_json() == ["a.gif", "b.gif"]


def test_html_no_longer_contains_bubble_controls_but_has_font(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="bubbleText"' not in body
    assert 'id="bubbleToggle"' not in body
    assert 'id="font"' in body
