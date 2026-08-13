"""Flask backend for the Overlay-Positions-UI.

Reads/writes ``Stream_Pet.json`` at the project root and serves idle StreamPet
GIFs for the Drag&Drop preview. Path traversal protection mirrors
``Overlay_project/overlay_server.py`` (``secure_filename`` + ``commonpath``).

The Pos-UI owns the ``stream_pet_config`` layout block only (position, height,
text size, speech-bubble offset, font). The bubble *text* and *toggle* plus
the GIF list / idle selection live in the Config-UI (``src/UI``). Both UIs
share ``Stream_Pet.json``; the Pos-UI ``POST /api/config`` writes the entire
body verbatim, so it must NOT drop keys it does not own (it preserves
``idle``/``animations``/``speech_bubble_text``/``speech_bubble_toggle``).

``GET /api/streampet/gifs`` lists the available ``.gif`` files in
``STREAM_PET_DIR`` for the preview fallback (when no ``idle`` is set, the
preview uses the first available GIF, or an empty placeholder box if the
directory is empty).

Run directly (``python -m twitchbot_runtime.overlay_pos_ui``) or via the
``create_app()`` factory for tests. Port resolution order:
``OVERLAY_POS_UI_PORT`` env var (highest priority, not persisted) →
``runtime.pos_ui.port`` in settings.json (resolved/persisted on first run
via :func:`resolve_port_or_exit`, falling back to ``DEFAULT_PORT``).
"""
from __future__ import annotations

import json
import os

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from twitchbot_runtime.ports import DEFAULT_PORTS, resolve_port_or_exit
from twitchbot_runtime.settings import load_settings

DEFAULT_PORT = 5003

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "Stream_Pet.json")
STREAM_PET_DIR = os.path.join(PROJECT_ROOT, "StreamPet")
SETTINGS_PATH = os.path.join(PROJECT_ROOT, "settings.json")


def _load_config() -> dict:
    # No DEFAULT_CONFIG: a missing Stream_Pet.json yields an empty object so
    # all consumers (Pos-UI, Config-UI, StreamPet, overlay.js) must be robust
    # against empty/missing keys (see plan: idle optional, .get-guards).
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _resolve_gif_path(config_value: str) -> str:
    """Resolve a ``Stream_Pet.json`` gif path (``StreamPet/Einhorn_Idle.gif``)
    to an absolute filesystem path inside ``STREAM_PET_DIR``.

    Only the basename is used, and the resolved path must remain inside
    ``STREAM_PET_DIR`` to prevent traversal outside the StreamPet folder.
    """
    safe_name = secure_filename(os.path.basename(config_value))
    if not safe_name:
        raise ValueError("Invalid gif filename")
    file_path = os.path.abspath(os.path.join(STREAM_PET_DIR, safe_name))
    if os.path.commonpath([file_path, STREAM_PET_DIR]) != STREAM_PET_DIR:
        raise ValueError("GIF path escapes StreamPet directory")
    return file_path


def _read_overlay_port_from_settings() -> int:
    """Return the overlay port from settings.json (default 5000).

    Never prompts or persists — only reads the persisted value or falls back
    to the default. Used for the "view in overlay" HTML link so the Pos-UI
    does not accidentally prompt for the overlay component.
    """
    try:
        settings = load_settings(SETTINGS_PATH)
    except Exception:
        return DEFAULT_PORTS["overlay"]
    runtime = settings.get("runtime", {})
    block = runtime.get("overlay", {}) if isinstance(runtime, dict) else {}
    if isinstance(block, dict) and isinstance(block.get("port"), int) and not isinstance(block.get("port"), bool):
        port = block["port"]
        if 1 <= port <= 65535:
            return port
    return DEFAULT_PORTS["overlay"]


def _render_page_html() -> str:
    """Render PAGE_HTML with the dynamic overlay link for the current port."""
    overlay_port = _read_overlay_port_from_settings()
    overlay_url = f"http://localhost:{overlay_port}/"
    return PAGE_HTML.replace("__OVERLAY_URL__", overlay_url).replace("__OVERLAY_PORT__", str(overlay_port))


PAGE_HTML = """<!doctype html>
<html lang=\"de\">
<head>
<meta charset=\"utf-8\">
<title>Overlay Positions-UI</title>
<style>
body { font-family: Arial, sans-serif; margin: 0; display: flex; }
#sidebar { width: 320px; padding: 12px; border-right: 1px solid #ccc; overflow-y: auto; }
#sidebar label { display: block; margin: 8px 0 2px; }
#sidebar input[type=\"range\"], #sidebar input[type=\"number\"], #sidebar input[type=\"text\"] { width: 100%; box-sizing: border-box; }
#canvas-wrap { flex: 1; padding: 12px; }
#canvas { position: relative; width: 100%; height: 80vh; background:
    repeating-conic-gradient(#eee 0% 25%, #fff 0% 50%) 50% / 24px 24px;
    border: 1px solid #888; overflow: hidden; }
#pet { position: absolute; user-select: none; cursor: grab; }
#pet.dragging { cursor: grabbing; }
#pet img { display: block; height: 100%; }
#speech { position: absolute; background: #fff; border: 1px solid #333; border-radius: 6px;
    padding: 4px 8px; font-size: 12px; white-space: nowrap; pointer-events: none; }
#status { margin-top: 12px; font-weight: bold; }
.open-overlay { margin-top: 16px; display: inline-block; }
</style>
</head>
<body>
<div id=\"sidebar\">
  <h2>StreamPet Konfiguration</h2>
  <label>Position X (0..1)</label><input id=\"posX\" type=\"number\" step=\"0.001\" min=\"0\" max=\"1\">
  <label>Position Y (0..1)</label><input id=\"posY\" type=\"number\" step=\"0.001\" min=\"0\" max=\"1\">
  <label>Hoehe (px)</label><input id=\"height\" type=\"range\" min=\"50\" max=\"600\" step=\"10\">
  <label>Textgroesse</label><input id=\"textSize\" type=\"range\" min=\"6\" max=\"48\" step=\"1\">
  <label>Sprechblase X (px relativ zu GIF)</label><input id=\"bubbleX\" type=\"number\" step=\"1\">
  <label>Sprechblase Y (px relativ zu GIF)</label><input id=\"bubbleY\" type=\"number\" step=\"1\">
  <label>Font (Schriftart)</label><input id=\"font\" type=\"text\">
  <button id=\"save\">Speichern</button>
  <span id=\"status\"></span>
  <a class=\"open-overlay\" href=\"__OVERLAY_URL__\" target=\"_blank\">Im Overlay ansehen (Port __OVERLAY_PORT__)</a>
</div>
<div id=\"canvas-wrap\">
  <div id=\"canvas\">
    <div id=\"pet\"><img id=\"petImg\" alt=\"StreamPet\"></div>
    <div id=\"speech\" style=\"display:none\"></div>
  </div>
</div>
<script>
let cfg = null;
const canvas = document.getElementById('canvas');
const pet = document.getElementById('pet');
const petImg = document.getElementById('petImg');
const speech = document.getElementById('speech');

async function load() {
  const r = await fetch('/api/config');
  cfg = await r.json();
  if (cfg.idle) {
    petImg.src = '/' + cfg.idle + '?t=' + Date.now();
    petImg.onerror = () => { petImg.style.display = 'none'; };
  } else {
    // No idle set: fall back to the first available GIF so the preview
    // still shows something for positioning. Empty dir -> hide the img;
    // #pet stays as a drag&drop placeholder.
    try {
      const gr = await fetch('/api/streampet/gifs');
      const gifs = gr.ok ? await gr.json() : [];
      if (Array.isArray(gifs) && gifs.length > 0) {
        petImg.src = '/StreamPet/' + gifs[0] + '?t=' + Date.now();
        petImg.onerror = () => { petImg.style.display = 'none'; };
      } else {
        petImg.style.display = 'none';
      }
    } catch (e) {
      petImg.style.display = 'none';
    }
  }
  syncControls();
  render();
}

function syncControls() {
  const sp = cfg.stream_pet_config || {};
  const pos = sp.position || {x:0, y:0};
  const bp = sp.speech_bubble_position || {x:60, y:-1};
  document.getElementById('posX').value = pos.x;
  document.getElementById('posY').value = pos.y;
  document.getElementById('height').value = sp.height || 300;
  document.getElementById('textSize').value = sp.text_size || 12;
  document.getElementById('bubbleX').value = bp.x;
  document.getElementById('bubbleY').value = bp.y;
  document.getElementById('font').value = sp.font || '';
}

function readControls() {
  const sp = cfg.stream_pet_config || (cfg.stream_pet_config = {});
  sp.position = {x: parseFloat(document.getElementById('posX').value) || 0,
                 y: parseFloat(document.getElementById('posY').value) || 0};
  sp.height = parseInt(document.getElementById('height').value, 10) || 300;
  sp.text_size = parseInt(document.getElementById('textSize').value, 10) || 12;
  sp.speech_bubble_position = {x: parseInt(document.getElementById('bubbleX').value, 10) || 0,
                                y: parseInt(document.getElementById('bubbleY').value, 10) || 0};
  sp.font = document.getElementById('font').value;
  // NOTE: idle / animations / speech_bubble_text / speech_bubble_toggle are
  // owned by the Config-UI. Do NOT touch them here so the roundtrip does
  // not destroy the Config-UI's data.
}

function render() {
  const sp = cfg.stream_pet_config || {};
  const pos = sp.position || {x:0, y:0};
  const h = sp.height || 300;
  const cw = canvas.clientWidth;
  const ch = canvas.clientHeight;
  pet.style.height = h + 'px';
  pet.style.left = (pos.x * cw) + 'px';
  pet.style.top = (pos.y * ch) + 'px';
  const bp = sp.speech_bubble_position || {x:60, y:-1};
  const petRight = (pos.x * cw) + pet.offsetWidth;
  const petTop = (pos.y * ch) + bp.y;
  speech.style.left = (petRight + bp.x) + 'px';
  speech.style.top = petTop + 'px';
  // Preview the bubble text only if it exists in cfg (Config-UI's domain);
  // otherwise hide it. font drives the preview fontFamily. The {username}
  // replace here is a static preview only ('User'); the real placeholder
  // resolution happens parent-side in the Runtime (ReactionEngine).
  const bubbleText = cfg.speech_bubble_text || '';
  speech.textContent = bubbleText.replace('{username}', 'User');
  speech.style.fontSize = (sp.text_size || 12) + 'px';
  speech.style.fontFamily = sp.font || 'Arial';
  speech.style.display = bubbleText && cfg.speech_bubble_toggle ? 'block' : 'none';
}

let dragging = false, offX = 0, offY = 0;
pet.addEventListener('mousedown', (e) => {
  dragging = true; pet.classList.add('dragging');
  offX = e.clientX - pet.offsetLeft;
  offY = e.clientY - pet.offsetTop;
  e.preventDefault();
});
window.addEventListener('mousemove', (e) => {
  if (!dragging) return;
  const rect = canvas.getBoundingClientRect();
  let x = e.clientX - rect.left - offX;
  let y = e.clientY - rect.top - offY;
  x = Math.max(0, Math.min(x, canvas.clientWidth - pet.offsetWidth));
  y = Math.max(0, Math.min(y, canvas.clientHeight - pet.offsetHeight));
  pet.style.left = x + 'px';
  pet.style.top = y + 'px';
  const sp = cfg.stream_pet_config || (cfg.stream_pet_config = {});
  sp.position = {x: x / canvas.clientWidth, y: y / canvas.clientHeight};
  document.getElementById('posX').value = sp.position.x.toFixed(3);
  document.getElementById('posY').value = sp.position.y.toFixed(3);
  render();
});
window.addEventListener('mouseup', () => { dragging = false; pet.classList.remove('dragging'); });

['posX','posY','height','textSize','bubbleX','bubbleY','font'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => { readControls(); render(); });
});

document.getElementById('save').addEventListener('click', async () => {
  readControls();
  const r = await fetch('/api/config', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(cfg)});
  const status = document.getElementById('status');
  if (r.ok) { status.textContent = 'Gespeichert.'; status.style.color = 'green'; }
  else { status.textContent = 'Fehler beim Speichern.'; status.style.color = 'red'; }
  setTimeout(() => status.textContent = '', 2000);
});

window.addEventListener('resize', render);
window.addEventListener('load', load);
</script>
</body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return _render_page_html()

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify(_load_config())

    @app.route("/api/config", methods=["POST"])
    def post_config():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Expected a JSON object"}), 400
        _save_config(data)
        return jsonify({"message": "Saved"})

    @app.route("/StreamPet/<path:filename>")
    def serve_stream_pet(filename):
        safe_name = secure_filename(filename)
        if not safe_name:
            return "Invalid filename", 400
        file_path = os.path.abspath(os.path.join(STREAM_PET_DIR, safe_name))
        if os.path.commonpath([file_path, STREAM_PET_DIR]) != STREAM_PET_DIR:
            return "File not found", 404
        if not os.path.exists(file_path):
            return "File not found", 404
        return send_from_directory(STREAM_PET_DIR, safe_name)

    @app.route("/StreamPet.gif")
    def serve_idle_gif():
        cfg = _load_config()
        idle = cfg.get("idle", "")
        try:
            file_path = _resolve_gif_path(idle)
        except ValueError as exc:
            return str(exc), 400
        if not os.path.exists(file_path):
            return "File not found", 404
        return send_file(file_path, mimetype="image/gif")

    @app.route("/api/streampet/gifs", methods=["GET"])
    def list_streampet_gifs():
        # Safe listing of all .gif files in STREAM_PET_DIR. Returns an empty
        # array when the directory is missing (preview fallback to empty box).
        if not os.path.isdir(STREAM_PET_DIR):
            return jsonify([])
        try:
            entries = os.listdir(STREAM_PET_DIR)
        except OSError:
            return jsonify([])
        gifs = sorted(
            name for name in entries
            if name.lower().endswith(".gif") and os.path.isfile(os.path.join(STREAM_PET_DIR, name))
        )
        return jsonify(gifs)

    return app


def main() -> int:
    env_port = os.environ.get("OVERLAY_POS_UI_PORT")
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            print(f"Invalid OVERLAY_POS_UI_PORT={env_port!r}; using default {DEFAULT_PORT}")
            port = DEFAULT_PORT
    else:
        port = resolve_port_or_exit("pos_ui", load_settings(SETTINGS_PATH), SETTINGS_PATH)
    app = create_app()
    app.run(host="127.0.0.1", port=port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
