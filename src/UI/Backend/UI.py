import json
import os
import sys
import threading

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder="../static", template_folder="../")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "../../.."))
SETTINGS_FILE = os.path.join(PROJECT_ROOT, "settings.json")
STREAM_PET_DIR = os.path.join(PROJECT_ROOT, "StreamPet")
STREAM_PET_CONFIG = os.path.join(PROJECT_ROOT, "Stream_Pet.json")

sys.path.insert(0, os.path.join(BASE_DIR, "../../.."))

from twitchbot_runtime.config_schema import build_config_schema_message  # noqa: E402
from twitchbot_runtime.ports import (  # noqa: E402
    DEFAULT_PORTS,
    get_effective_ports,
    resolve_port_or_exit,
)
from twitchbot_runtime.settings import load_settings, save_settings  # noqa: E402

VALID_PORT_COMPONENTS = ("overlay", "webui", "webhook", "pos_ui", "oauth")
_OAUTH_DEFAULT_PORT = DEFAULT_PORTS["oauth"]


def _oauth_redirect_uri(oauth_port: int) -> str:
    """Build the exact OAuth redirect URI for the given OAuth port."""
    return f"http://localhost:{oauth_port}/oauth/callback"

TRIGGER_HINTS = {
    "command": {
        "scope": "user:read:chat + user:bot (Bot), channel:bot (Broadcaster)",
        "required_by": "Bot + Broadcaster",
        "hint": "EventSub: channel.chat.message. Bot braucht user:read:chat+user:bot; Broadcaster muss channel:bot freigeben.",
    },
    "new_chatter": {
        "scope": "user:read:chat + user:bot (Bot), channel:bot (Broadcaster)",
        "required_by": "Bot + Broadcaster",
        "hint": "Inaktivitäts-Fenster (channel.chat.message): matched, wenn der Chatter länger als 'time' Sekunden nicht gesprochen hat (oder noch nie). Bot braucht user:read:chat+user:bot; Broadcaster muss channel:bot freigeben.",
    },
    "first_time_chatter": {
        "scope": "user:read:chat + user:bot (Bot), channel:bot (Broadcaster)",
        "required_by": "Bot + Broadcaster",
        "hint": "Twitch chatter_is_new-Flag (channel.chat.message). Keine Konfiguration nötig. Bot braucht user:read:chat+user:bot; Broadcaster muss channel:bot freigeben.",
    },
    "channel_point_reward": {
        "scope": "channel:read:redemptions",
        "required_by": "Broadcaster",
        "hint": "Broadcaster muss channel:read:redemptions freigeben. EventSub: channel.channel_points_custom_reward_redemption.add.",
    },
    "follow": {
        "scope": "moderator:read:followers (Bot)",
        "required_by": "Bot",
        "hint": "Bot (als Mod) muss moderator:read:followers haben. EventSub: channel.follow.",
    },
    "sub": {
        "scope": "channel:read:subscriptions (Broadcaster)",
        "required_by": "Broadcaster",
        "hint": "Broadcaster muss channel:read:subscriptions freigeben. EventSub: channel.subscribe.",
    },
    "cheer": {
        "scope": "bits:read (Broadcaster)",
        "required_by": "Broadcaster",
        "hint": "Broadcaster muss bits:read freigeben. EventSub: channel.cheer. Optional min_bits filter.",
    },
    "raid": {
        "scope": "keiner",
        "required_by": "niemand",
        "hint": "Keine Freigabe nötig. EventSub: channel.raid. Optional min_viewers filter.",
    },
    "time": {
        "scope": "keiner",
        "required_by": "niemand",
        "hint": "Lokaler Timer, kein Twitch-Event.",
    },
    "role": {
        "scope": "keiner",
        "required_by": "niemand",
        "hint": "Rollen-Check (mod/broadcaster/vip/subscriber). Broadcaster darf immer. Nutzbar in When (Trigger) und if.when (Reaktionsbaum) für pro-Case-Rollen.",
    },
}


def _settings_path():
    return os.path.abspath(SETTINGS_FILE)


def _load_streampet_config() -> dict:
    """Read ``Stream_Pet.json``; empty dict if missing/corrupt (no default)."""
    if not os.path.exists(STREAM_PET_CONFIG):
        return {}
    try:
        with open(STREAM_PET_CONFIG, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_streampet_config(data: dict) -> None:
    with open(STREAM_PET_CONFIG, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _list_streampet_gifs() -> list:
    """Safe sorted list of ``.gif`` basenames in ``STREAM_PET_DIR`` (empty if missing)."""
    if not os.path.isdir(STREAM_PET_DIR):
        return []
    try:
        entries = os.listdir(STREAM_PET_DIR)
    except OSError:
        return []
    return sorted(
        name for name in entries
        if name.lower().endswith(".gif") and os.path.isfile(os.path.join(STREAM_PET_DIR, name))
    )


@app.route('/api/config_schema', methods=['GET'])
def get_config_schema():
    """Liefert das Runtime-Konfigurationsschema zum Rendern von Formularen."""
    try:
        return jsonify(build_config_schema_message())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/trigger_hints', methods=['GET'])
def get_trigger_hints():
    """Liefert pro Trigger-Typ Hinweise zu benötigtem Scope/Freigabe."""
    return jsonify(TRIGGER_HINTS)


@app.route('/api/commands', methods=['GET'])
def get_commands():
    """Lädt die Trigger aus settings.json und gibt sie zurück."""
    try:
        settings = load_settings(_settings_path())
        return jsonify({"commands": settings.get("triggers", [])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/commands', methods=['POST'])
def save_commands():
    """Speichert die Befehle in settings.json unter dem Schlüssel triggers."""
    try:
        data = request.json or {}
        settings = load_settings(_settings_path())
        settings["triggers"] = data.get("commands", [])
        save_settings(settings, _settings_path())
        return jsonify({"message": "Commands saved successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Gibt die gesamte settings.json zurück."""
    try:
        settings = load_settings(_settings_path())
        return jsonify(settings)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def save_settings_route():
    """Speichert die gesamte settings.json."""
    try:
        data = request.json or {}
        save_settings(data, _settings_path())
        return jsonify({"message": "Settings saved successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/exit', methods=['POST'])
def save_and_exit():
    """Speichert die Trigger (Merge) und beendet das Programm.

    Der Frontend-Buffer (``jsonBuffer`` aus ``GET /api/commands``) nutzt den
    Schluessel ``commands``; direkte API-Aufrufer koennen ``triggers``
    senden. Beide werden in die bestehende ``settings.json`` unter
    ``triggers`` gemerged — ``runtime``, ``features``, ``twitch`` und Ports
    bleiben unangetastet (im Gegensatz zum frueheren destruktiven Replace).
    """
    try:
        data = request.json or {}
        settings = load_settings(_settings_path())
        if "commands" in data:
            settings["triggers"] = data.get("commands", [])
        elif "triggers" in data:
            settings["triggers"] = data.get("triggers", [])

        def shutdown_server():
            os._exit(0)

        threading.Thread(target=shutdown_server, daemon=True).start()

        save_settings(settings, _settings_path())

        return jsonify({"message": "Saved and exiting!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/streampet', methods=['GET'])
def get_streampet():
    """Liefert den Inhalt von ``Stream_Pet.json`` (leeres Objekt wenn fehlt)."""
    return jsonify(_load_streampet_config())


@app.route('/api/streampet', methods=['POST'])
def save_streampet():
    """Speichert ``Stream_Pet.json`` als Merge über die bestehende Datei.

    Die Config-UI schickt nur ihre 4 Keys (``idle``, ``animations``,
    ``speech_bubble_text``, ``speech_bubble_toggle``); der ``stream_pet_config``
    Block (Pos-UI-Domain) bleibt unangetastet, weil nur Top-Level-Keys aus dem
    Body über existing gelegt werden.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400
    existing = _load_streampet_config()
    existing.update(data)
    try:
        _save_streampet_config(existing)
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"message": "StreamPet config saved"})


@app.route('/api/streampet/gifs', methods=['GET'])
def list_streampet_gifs():
    """Sichere GIF-Liste in ``StreamPet/`` (leer wenn Verzeichnis fehlt)."""
    return jsonify(_list_streampet_gifs())


@app.route('/api/streampet/upload', methods=['POST'])
def upload_streampet_gif():
    """Sicherer GIF-Upload nach ``StreamPet/``.

    Validierung: Datei vorhanden, ``.gif``-Endung, ``secure_filename`` und
    ``commonpath``-Check gegen ``STREAM_PET_DIR``. Name-Kollision ueberschreibt
    still (UI-Hinweis wird vom Frontend gegeben). Rueckgabe-Pfad-Format
    ``StreamPet/<basename>`` passt zu ``overlay_server.py`` Route
    ``/StreamPet/<filename>`` und ``StreamPet.idle_gif_path``-Aufloesung.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    safe_name = secure_filename(file.filename)
    if not safe_name or not safe_name.lower().endswith('.gif'):
        return jsonify({"error": "Only .gif files are allowed"}), 400
    try:
        os.makedirs(STREAM_PET_DIR, exist_ok=True)
    except OSError as e:
        return jsonify({"error": f"Cannot create StreamPet dir: {e}"}), 500
    target_path = os.path.abspath(os.path.join(STREAM_PET_DIR, safe_name))
    if os.path.commonpath([target_path, STREAM_PET_DIR]) != STREAM_PET_DIR:
        return jsonify({"error": "Invalid path"}), 400
    try:
        file.save(target_path)
    except OSError as e:
        return jsonify({"error": f"Save failed: {e}"}), 500
    return jsonify({"filename": safe_name, "path": f"StreamPet/{safe_name}"})


@app.route('/api/ports', methods=['GET'])
def get_ports():
    """Liefert Status (port/default/frei) aller 5 konfigurierbaren Ports."""
    try:
        settings = load_settings(_settings_path())
        snapshot = get_effective_ports(settings)
        oauth_warning = None
        oauth_port = snapshot.get("oauth", {}).get("port", _OAUTH_DEFAULT_PORT)
        if oauth_port != _OAUTH_DEFAULT_PORT:
            oauth_warning = (
                f"OAuth-Port ist {oauth_port}, nicht {_OAUTH_DEFAULT_PORT}. "
                "Die Redirect URI in der Twitch Developer Console muss auf "
                f"http://localhost:{oauth_port}/oauth/callback passen, "
                "sonst schlägt die Autorisierung fehl."
            )
        return jsonify({
            "ports": snapshot,
            "oauth_warning": oauth_warning,
            "oauth_redirect_uri": _oauth_redirect_uri(oauth_port),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ports', methods=['POST'])
def save_port():
    """Persistiert einen einzelnen Port-Wert in settings.json.

    Body: ``{"component": "overlay", "port": 5050}``. Validiert int 1..65535.
    OAuth-Änderungen liefern ein ``warning``-Feld über die Twitch-Redirect-URI.
    """
    try:
        data = request.get_json(silent=True) or {}
        component = data.get("component")
        raw_port = data.get("port")
        if component not in VALID_PORT_COMPONENTS:
            return jsonify({"error": f"Unknown component: {component}"}), 400
        if isinstance(raw_port, bool) or not isinstance(raw_port, int):
            return jsonify({"error": "port must be an integer"}), 400
        if raw_port < 1 or raw_port > 65535:
            return jsonify({"error": "port must be in 1..65535"}), 400

        settings = load_settings(_settings_path())
        runtime = settings.setdefault("runtime", {})
        block = runtime.get(component)
        if not isinstance(block, dict):
            block = {}
            runtime[component] = block
        block["port"] = raw_port
        save_settings(settings, _settings_path())

        snapshot = get_effective_ports(settings)
        warning = None
        if component == "oauth" and raw_port != _OAUTH_DEFAULT_PORT:
            warning = (
                f"OAuth-Port ist jetzt {raw_port}. Die Redirect URI in der "
                "Twitch Developer Console muss auf "
                f"http://localhost:{raw_port}/oauth/callback angepasst werden, "
                "sonst schlägt die Autorisierung fehl."
            )
        oauth_port = snapshot.get("oauth", {}).get("port", _OAUTH_DEFAULT_PORT)
        return jsonify({
            "ports": snapshot,
            "warning": warning,
            "oauth_redirect_uri": _oauth_redirect_uri(oauth_port),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


FEATURE_COMPONENTS = ("moderation", "overlay", "webui")


def _features_defaults(features: dict) -> dict:
    """Normalisiere die ``features``-Sektion auf die Runtime-Defaults.

    Die Defaults (``moderation``/``webui`` an, ``overlay`` aus) muessen mit
    ``bot.py._register_features`` uebereinstimmen; fehlt ein Block, greift der
    jeweilige Default.
    """
    return {
        "moderation": {"enabled": features.get("moderation", {}).get("enabled", True)},
        "overlay": {"enabled": features.get("overlay", {}).get("enabled", False)},
        "webui": {"enabled": features.get("webui", {}).get("enabled", True)},
    }


@app.route('/api/features', methods=['GET'])
def get_features():
    """Liefert die drei Runtime-Feature-Toggles mit normalisierten Defaults."""
    try:
        settings = load_settings(_settings_path())
        features = settings.get("features", {}) or {}
        if not isinstance(features, dict):
            features = {}
        return jsonify(_features_defaults(features))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/features', methods=['POST'])
def save_features():
    """Setzt genau einen Feature-Toggle (Merge, nicht Replace).

    Body: ``{"component": "overlay", "enabled": true}``. Strikte Bool-Pruefung
    verhindert den ``bool("false") == True``-Footgun — JSON-Strings werden
    abgelehnt. Nur ``features.<component>.enabled`` wird geschrieben, der Rest
    der ``settings.json`` bleibt unangetastet.
    """
    try:
        data = request.get_json(silent=True) or {}
        if "component" not in data or "enabled" not in data:
            return jsonify({"error": "component and enabled required"}), 400
        if not isinstance(data["enabled"], bool):
            return jsonify({"error": "enabled must be a boolean"}), 400
        component = data["component"]
        if component not in FEATURE_COMPONENTS:
            return jsonify({"error": f"Unknown feature: {component}"}), 400

        settings = load_settings(_settings_path())
        features = settings.setdefault("features", {})
        if not isinstance(features, dict):
            features = {}
            settings["features"] = features
        block = features.get(component)
        if not isinstance(block, dict):
            block = {}
            features[component] = block
        block["enabled"] = data["enabled"]
        save_settings(settings, _settings_path())
        return jsonify({"features": _features_defaults(features)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/')
def serve_ui():
    """Serviert die HTML-Datei."""
    return send_from_directory(os.path.join(BASE_DIR, '../'), 'index.html')

if __name__ == '__main__':
    port = resolve_port_or_exit("webui", load_settings(_settings_path()), _settings_path())
    app.run(debug=False, use_reloader=False, port=port)
