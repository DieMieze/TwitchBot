import os

from flask import Flask, render_template, send_file, send_from_directory
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(__file__)
STREAM_PET_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "StreamPet"))
CONFIG_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "Stream_Pet.json"))


def create_app():
    """Factory für die Overlay-Flask-App + SocketIO.

    Gibt ein ``(app, socketio)``-Tuple zurück, weil ``flask_socketio.SocketIO``
    sich nicht zuverlässig in ``app.extensions`` einträgt — daher keine
    Referenzierung über ``app.extensions["socketio"]``.

    Modul-Globals ``app``/``socketio`` werden aus der Factory erzeugt, damit
    bestehende Importe (``from Overlay_project.overlay_server import app,
    socketio``) unverändert funktionieren (Kompat-Alias, siehe Plan P3).
    """
    app = Flask(__name__, static_folder="static")
    socketio = SocketIO(app, cors_allowed_origins="*")

    @app.route("/StreamPet/<path:filename>")
    def serve_file(filename):
        # Path-Traversal-Schutz: filename wird über secure_filename bereinigt
        # und der finale Pfad muss innerhalb von STREAM_PET_DIR liegen.
        safe_name = secure_filename(filename)
        if not safe_name:
            return "Invalid filename", 400
        file_path = os.path.abspath(os.path.join(STREAM_PET_DIR, safe_name))
        if os.path.commonpath([file_path, STREAM_PET_DIR]) != STREAM_PET_DIR:
            return "File not found", 404
        if not os.path.exists(file_path):
            return "File not found", 404
        return send_from_directory(STREAM_PET_DIR, safe_name)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory("static", "favicon.ico")

    @app.route("/config.json")
    def stream_pet_config():
        # CWD-unabhängig: Pfad zur Konfiguration BASE_DIR-basiert (nicht relativ).
        return send_file(CONFIG_PATH, mimetype="application/json")

    return app, socketio


app, socketio = create_app()
