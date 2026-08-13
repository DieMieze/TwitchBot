# overlay_helpers.py (z. B. extra Datei oder ganz oben in overlay.py)

import time
import urllib.request


def open_browser_when_ready(url="http://127.0.0.1:5000/"):
    for _ in range(10):
        try:
            urllib.request.urlopen(url)
            # webbrowser.open(url)            # comment out later
            break
        except Exception:
            time.sleep(0.5)

def handle_signals(overlay_logger, running_event, socketio, signum, frame):
    """Signalhandler für den Overlay-Subprozess (SIGTERM/SIGINT).

    Verantwortlich NUR für den Subprocess-Lifecycle, nicht generell nutzbar:
    er ist eng an die ``OverlayFacade._run_overlay``-Signatur gekoppelt
    (``running_event`` = multiprocessing.Event, ``socketio`` = der im
    Subprozess erzeugte SocketIO-Handler). Aufgerufen wird er nur, wenn der
    Kindprozess ein echtes Terminal-Signal empfängt (Linux: ``kill``,
    Windows: Ctrl-C im Konsolenfenster). Er ist NICHT der primäre Stop-Pfad —
    dieser läuft plattformneutral über ``running_event.clear()`` + ``"STOP"``
    in der Queue (siehe ``OverlayFacade.stop``). Unter Windows wird dieser
    Handler bei ``process.terminate()`` (TerminateProcess) nicht ausgelöst.
    """
    overlay_logger.info(f"Signal {signum} empfangen. Beende Overlay-Prozess...")
    running_event.clear()  # Beende die Schleife
    socketio.stop()
