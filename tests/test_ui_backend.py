import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import io
import json

try:
    from flask import Flask  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

import pytest

pytestmark = pytest.mark.skipif(not HAS_FLASK, reason="Flask not installed")

if HAS_FLASK:
    from UI.Backend import UI as ui_module


def _write_settings(path: Path, settings: dict) -> None:
    path.write_text(json.dumps(settings), encoding="utf-8")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"runtime": {"execution_mode": "test"}, "triggers": []})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))
    return ui_module.app.test_client()


@pytest.fixture()
def streampet_isolated(tmp_path, monkeypatch):
    stream_pet_dir = tmp_path / "StreamPet"
    stream_pet_dir.mkdir()
    config_path = tmp_path / "Stream_Pet.json"
    monkeypatch.setattr(ui_module, "STREAM_PET_DIR", str(stream_pet_dir))
    monkeypatch.setattr(ui_module, "STREAM_PET_CONFIG", str(config_path))
    return {"dir": stream_pet_dir, "config": config_path}


def test_get_config_schema_returns_runtime_schema(client):
    resp = client.get("/api/config_schema")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["type"] == "config_schema"
    assert "commands" in data["schema"]["properties"]


def test_get_commands_returns_triggers(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"triggers": [{"name": "hello"}]})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.get("/api/commands")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"commands": [{"name": "hello"}]}


def test_post_commands_writes_triggers(client):
    resp = client.post("/api/commands", json={"commands": [{"name": "test"}]})
    assert resp.status_code == 200

    resp = client.get("/api/commands")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"commands": [{"name": "test"}]}


def test_get_settings_returns_full_settings(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    payload = {
        "runtime": {"execution_mode": "test"},
        "features": {"overlay": {"enabled": True}},
        "triggers": [],
    }
    _write_settings(settings_path, payload)
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == payload


def test_post_settings_saves(client):
    payload = {
        "runtime": {"execution_mode": "silent"},
        "features": {"moderation": {"enabled": True}},
        "triggers": [{"name": "saved"}],
    }
    resp = client.post("/api/settings", json=payload)
    assert resp.status_code == 200

    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.get_json() == payload


def test_api_exit_saves_settings(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {
            "features": {"overlay": {"enabled": True}},
            "runtime": {"execution_mode": "silent"},
            "triggers": [],
        },
    )
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    called = {"shutdown": False}

    def fake_exit(code=0):
        called["shutdown"] = True

    monkeypatch.setattr(ui_module.os, "_exit", fake_exit)

    resp = client.post("/api/exit", json={"commands": [{"name": "x"}]})

    assert resp.status_code == 200
    assert resp.get_json()["message"] == "Saved and exiting!"
    assert called["shutdown"] is True

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["triggers"] == [{"name": "x"}]
    assert saved["features"]["overlay"]["enabled"] is True
    assert saved["runtime"]["execution_mode"] == "silent"


def test_api_exit_triggers_key_merges(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {"runtime": {"execution_mode": "test"}, "features": {"overlay": {"enabled": True}}, "triggers": []},
    )
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    monkeypatch.setattr(ui_module.os, "_exit", lambda code=0: None)

    resp = client.post("/api/exit", json={"runtime": {"execution_mode": "production"}, "triggers": [{"name": "direct"}]})

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["triggers"] == [{"name": "direct"}]
    assert saved["features"]["overlay"]["enabled"] is True
    assert saved["runtime"]["execution_mode"] == "test"


def test_api_exit_preserves_when_neither_key(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {"runtime": {"execution_mode": "test"}, "features": {"overlay": {"enabled": True}}, "triggers": [{"name": "keep"}]},
    )
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))
    monkeypatch.setattr(ui_module.os, "_exit", lambda code=0: None)

    resp = client.post("/api/exit", json={"unrelated": True})

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["triggers"] == [{"name": "keep"}]
    assert saved["features"]["overlay"]["enabled"] is True


def test_api_upload_removed_returns_404(client):
    # The insecure /api/upload route was removed (no secure_filename, wrote to
    # project root). It must now 404.
    resp = client.post("/api/upload")
    assert resp.status_code == 404


def test_get_streampet_returns_empty_when_file_missing(client, streampet_isolated):
    assert not streampet_isolated["config"].exists()
    resp = client.get("/api/streampet")
    assert resp.status_code == 200
    assert resp.get_json() == {}


def test_post_streampet_merges_preserving_stream_pet_config(client, streampet_isolated):
    # Pre-existing config owned by Pos-UI (stream_pet_config block).
    pre = {
        "stream_pet_config": {
            "position": {"x": 0.1, "y": 0.2},
            "height": 250,
            "font": "Verdana",
            "text_size": 14,
            "speech_bubble_position": {"x": 5, "y": -10},
        }
    }
    streampet_isolated["config"].write_text(json.dumps(pre), encoding="utf-8")

    # Config-UI posts only its 4 keys.
    payload = {
        "idle": "StreamPet/pet.gif",
        "animations": {"wave": "StreamPet/wave.gif"},
        "speech_bubble_text": "Hi {username}",
        "speech_bubble_toggle": True,
    }
    resp = client.post("/api/streampet", json=payload)
    assert resp.status_code == 200

    saved = json.loads(streampet_isolated["config"].read_text(encoding="utf-8"))
    # Config-UI keys written.
    assert saved["idle"] == "StreamPet/pet.gif"
    assert saved["animations"] == {"wave": "StreamPet/wave.gif"}
    assert saved["speech_bubble_text"] == "Hi {username}"
    assert saved["speech_bubble_toggle"] is True
    # Pos-UI block preserved (merge, not overwrite).
    assert saved["stream_pet_config"] == pre["stream_pet_config"]


def test_post_streampet_rejects_non_object(client):
    resp = client.post("/api/streampet", json=["not", "an", "object"])
    assert resp.status_code == 400


def test_get_streampet_gifs_empty_when_dir_empty(client, streampet_isolated):
    resp = client.get("/api/streampet/gifs")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_get_streampet_gifs_lists_gifs_sorted(client, streampet_isolated):
    d = streampet_isolated["dir"]
    (d / "z.gif").write_bytes(b"GIF89a")
    (d / "a.gif").write_bytes(b"GIF89a")
    (d / "ignore.txt").write_bytes(b"nope")
    resp = client.get("/api/streampet/gifs")
    assert resp.status_code == 200
    assert resp.get_json() == ["a.gif", "z.gif"]


def test_post_streampet_upload_saves_gif(client, streampet_isolated):
    data = {
        "file": (io.BytesIO(b"GIF89a pixels"), "pet.gif"),
    }
    resp = client.post(
        "/api/streampet/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["filename"] == "pet.gif"
    assert body["path"] == "StreamPet/pet.gif"
    saved = streampet_isolated["dir"] / "pet.gif"
    assert saved.exists()
    assert saved.read_bytes() == b"GIF89a pixels"


def test_post_streampet_upload_rejects_non_gif(client, streampet_isolated):
    data = {"file": (io.BytesIO(b"plain"), "notes.txt")}
    resp = client.post(
        "/api/streampet/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_post_streampet_upload_rejects_missing_file(client, streampet_isolated):
    resp = client.post("/api/streampet/upload", content_type="multipart/form-data")
    assert resp.status_code == 400


def test_post_streampet_upload_sanitizes_traversal(client, streampet_isolated):
    # secure_filename neutralizes "../escape.gif" -> "escape.gif" inside dir.
    data = {"file": (io.BytesIO(b"GIF89a"), "../../../escape.gif")}
    resp = client.post(
        "/api/streampet/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert ".." not in body["path"]
    assert body["filename"] == "escape.gif"
    saved = streampet_isolated["dir"] / "escape.gif"
    assert saved.exists()


def test_api_exit_get_commands_no_longer_reads_legacy_commands_key(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {"commands": [{"name": "legacy"}], "triggers": [{"name": "runtime"}]},
    )
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.get("/api/commands")
    assert resp.status_code == 200
    assert resp.get_json() == {"commands": [{"name": "runtime"}]}


def test_get_trigger_hints_returns_mapping_for_all_types(client):
    resp = client.get("/api/trigger_hints")
    assert resp.status_code == 200
    data = resp.get_json()
    for trigger_type in ("command", "new_chatter", "first_time_chatter", "channel_point_reward", "follow", "sub", "cheer", "raid", "time"):
        assert trigger_type in data
        assert "hint" in data[trigger_type]
        assert "scope" in data[trigger_type]
    assert "min_bits" in data["cheer"]["hint"]
    assert "min_viewers" in data["raid"]["hint"]
    assert "Inaktivität" in data["new_chatter"]["hint"]
    assert "chatter_is_new" in data["first_time_chatter"]["hint"]


def test_get_ports_returns_all_components(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"runtime": {"overlay": {"port": 6000}}})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.get("/api/ports")
    assert resp.status_code == 200
    data = resp.get_json()
    ports = data["ports"]
    assert set(ports.keys()) == {"overlay", "webui", "webhook", "pos_ui", "oauth"}
    assert ports["overlay"]["port"] == 6000
    assert ports["overlay"]["default"] == 5000
    assert isinstance(ports["overlay"]["free"], bool)
    assert ports["webui"]["port"] == 5001
    assert data["oauth_warning"] is None
    assert data["oauth_redirect_uri"] == "http://localhost:5003/oauth/callback"


def test_get_ports_oauth_warning_when_port_differs(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"runtime": {"oauth": {"port": 5010}}})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.get("/api/ports")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "5010" in data["oauth_warning"]
    assert "Redirect URI" in data["oauth_warning"]
    assert data["oauth_redirect_uri"] == "http://localhost:5010/oauth/callback"


def test_post_ports_persists_valid_port(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"runtime": {}})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.post("/api/ports", json={"component": "overlay", "port": 5050})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ports"]["overlay"]["port"] == 5050

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["runtime"]["overlay"]["port"] == 5050


def test_post_ports_rejects_unknown_component(client):
    resp = client.post("/api/ports", json={"component": "nope", "port": 5000})
    assert resp.status_code == 400


def test_post_ports_rejects_non_integer(client):
    resp = client.post("/api/ports", json={"component": "overlay", "port": "abc"})
    assert resp.status_code == 400


def test_post_ports_rejects_out_of_range(client):
    resp = client.post("/api/ports", json={"component": "overlay", "port": 70000})
    assert resp.status_code == 400


def test_post_ports_oauth_returns_warning(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"runtime": {}})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.post("/api/ports", json={"component": "oauth", "port": 5010})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["warning"] is not None
    assert "5010" in data["warning"]
    assert "Redirect URI" in data["warning"]
    assert data["oauth_redirect_uri"] == "http://localhost:5010/oauth/callback"


def test_get_features_returns_defaults(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"runtime": {"execution_mode": "test"}, "triggers": []})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.get("/api/features")
    assert resp.status_code == 200
    assert resp.get_json() == {
        "moderation": {"enabled": True},
        "overlay": {"enabled": False},
        "webui": {"enabled": True},
    }


def test_get_features_returns_defaults_when_features_absent(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"runtime": {"execution_mode": "test"}})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.get("/api/features")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["moderation"]["enabled"] is True
    assert data["overlay"]["enabled"] is False
    assert data["webui"]["enabled"] is True


def test_get_features_returns_persisted(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {"features": {"overlay": {"enabled": True}, "moderation": {"enabled": False}}, "triggers": []},
    )
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.get("/api/features")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["overlay"]["enabled"] is True
    assert data["moderation"]["enabled"] is False
    assert data["webui"]["enabled"] is True


def test_post_features_persists_merge(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        {
            "runtime": {"execution_mode": "silent"},
            "triggers": [{"name": "keep"}],
            "features": {"moderation": {"enabled": True}},
        },
    )
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.post("/api/features", json={"component": "overlay", "enabled": True})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["features"]["overlay"]["enabled"] is True
    assert data["features"]["moderation"]["enabled"] is True

    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["features"]["overlay"]["enabled"] is True
    assert saved["features"]["moderation"]["enabled"] is True
    assert saved["runtime"]["execution_mode"] == "silent"
    assert saved["triggers"] == [{"name": "keep"}]


def test_post_features_rejects_unknown_component(client):
    resp = client.post("/api/features", json={"component": "nope", "enabled": True})
    assert resp.status_code == 400


def test_post_features_rejects_missing_fields(client):
    resp = client.post("/api/features", json={"component": "overlay"})
    assert resp.status_code == 400
    resp = client.post("/api/features", json={"enabled": True})
    assert resp.status_code == 400


def test_post_features_rejects_non_bool_enabled(client):
    resp = client.post("/api/features", json={"component": "overlay", "enabled": "true"})
    assert resp.status_code == 400


def test_post_features_rejects_non_bool_int(client):
    resp = client.post("/api/features", json={"component": "overlay", "enabled": 1})
    assert resp.status_code == 400


def test_post_features_rejects_non_dict_features_block(client, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, {"features": "not-a-dict", "triggers": []})
    monkeypatch.setattr(ui_module, "SETTINGS_FILE", str(settings_path))

    resp = client.post("/api/features", json={"component": "overlay", "enabled": True})
    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["features"]["overlay"]["enabled"] is True


def test_get_config_schema_includes_new_role_enums(client):
    resp = client.get("/api/config_schema")
    assert resp.status_code == 200
    data = resp.get_json()
    roles_enum = data["schema"]["properties"]["commands"]["items"]["properties"]["roles"]["items"]["enum"]
    assert "everyone" in roles_enum
    assert "subscriber" in roles_enum
    assert "vip" in roles_enum
    assert "mod" in roles_enum
    assert "broadcaster" in roles_enum
