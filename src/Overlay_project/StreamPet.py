import json
import os
import time
from queue import Queue  # threadsafe, kein multiprocessing

from PIL import Image


class StreamPet:
    """GIF-Animations-Zustandsmaschine für das StreamPet-Overlay.

    StreamPet wird vom Subprozess (`OverlayFacade._run_overlay`) getrieben. Die
    eigentliche Bildsynthese passiert im Browser (`overlay.js`); Python steuert
    nur den **Animations-Index** (welche Animation läuft, Frame-Position,
    Sprechblase) und serialisiert den Zustand über :meth:`draw`.

    Zwei Queue-Konzepte existieren nebeneinander und werden bewusst getrennt:

    * ``facade.queue`` (:class:`multiprocessing.Queue`) — Eltern→Kind-IPC. Der
      Hauptprozess legt hereinkommende Overlay-Aktionen
      (``{"action": "StreamPet", "data": {...}}``) sowie das ``"STOP"``-
      Steuerkommando ab. Der ``update_loop`` in ``facade.py`` entleert sie und
      reicht Animationen an :meth:`add_animation` weiter.
    * ``self.queue`` (:class:`queue.Queue`, threading) — intern für die
      Animations-Zustandsmaschine. :meth:`add_animation` legt Animationen
      hier ab; :meth:`update` holt sie gestaffelt ab (ein Wechsel pro
      Frame-Grenze, ``loading_next`` verhindert Mid-Animation-Preemption).

    Der ``"STOP"``-String liegt *nur* in ``facade.queue`` (Kontrollkanal) und
    gelangt nie in ``self.queue`` (Datenkanal).
    """

    def __init__(self, idle_gif_path, animations, overlay_logger, scale=1):
        """
        Initialisiert das StreamPet.
        :param idle_gif_path: Pfad zum Standard-"idle"-GIF. ``None``/"" bedeuten:
            kein Idle gesetzt -> leere Ein-Frame-Fallback-Animation (transparent),
            kein Bildzugriff, kein Crash (siehe plan: idle optional).
        :param animations: Dictionary mit Animationen (z. B. {"dance": "path/to/dance.gif"}).
            Leeres Dict ist gueltig.
        :param overlay_logger: Logger für den Overlay-Prozess.
        :param scale: Skalierungsfaktor (unbenutzt für die Index-Steuerung,
            Reserved für künftige Layout-Anpassungen).
        """
        self.queue = Queue()  # Eigene Queue für Animationen (threading, Datenkanal)
        self.logger = overlay_logger  # Logger für den Overlay-Prozess

        print(f"{self.logger}")

        # idle optional: None/"" -> kein Pfad, preload_animations legt eine
        # leere Ein-Frame-Animation direkt an (ohne Image.open-Aufruf).
        if idle_gif_path:
            self.idle_gif_path = os.path.join(os.path.dirname(__file__), "../..", idle_gif_path)  # Absoluter Pfad
        else:
            self.idle_gif_path = None
        self.animations = {key: os.path.join(os.path.dirname(__file__), "../..", path) for key, path in (animations or {}).items()}
        self.config_path = os.path.join(os.path.dirname(__file__), "../..", "Stream_Pet.json")  # Absoluter Pfad zur Konfigurationsdatei
        self.config = {}

        try:
            with open(self.config_path, encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception as e:
            self.logger.error(f"❌ Fehler beim Laden der Konfigurationsdatei: {e}")
            self.config = {}

        self.current_animation = None
        self.current_frame = 0
        self.last_frame_time = time.time()
        self.fps = 60  # FPS für die Animationen
        self.frames = None # Frames des aktuellen GIFs


        self.preloaded_animations = {}  # Speicher für vorab geladene Animationen
        self.loading_next = False  # Flag, ob die nächste Animation geladen wird

        # Lade alle Animationen vor
        self.preload_animations()

        # Invariant nach preload_animations: preloaded_animations["idle"]
        # existiert immer (echtes GIF-Metadata oder leerer Ein-Frame-Fallback),
        # daher kein KeyError in den Folgezeilen moeglich.
        self.next_frames = self.preloaded_animations["idle"]["frames"]  # Standardmäßig Idle-Frames
        self.next_fps = self.preloaded_animations["idle"]["fps"]        # Standardmäßig Idle-FPS
        self.frames = self.preloaded_animations["idle"]["frames"]       # Aktuelle Frames auf Idle setzen
        self.fps = self.preloaded_animations["idle"]["fps"]             # FPS auf Idle setzen

        self.current_animation_name = "idle"
        self.next_animation_name = "idle"
        self.animation_data = None
        self.next_animation_data = None


    def preload_animations(self):
        """Liest Frame-Zahl und FPS aller GIFs vorab (nur Metadaten, keine Pixel).

        Wichtig: Python rendert keine Bilder. Der Browser decodiert die GIFs
        selbst (``overlay.js`` via ``gifuct-js``); Python treuert nur den
        **Frame-Index** für die Zustandsmaschine. ``fps`` steuert hier, wie
        schnell :meth:`update` den internen Zähler weiterschaltet — die
        tatsächliche Anzeige-Framerate im Browser kommt von
        ``requestAnimationFrame`` (siehe Plan P2: Client treibt Frames).

        Invariant nach diesem Aufruf: ``preloaded_animations["idle"]``
        existiert immer. Bei nicht gesetztem idle (``idle_gif_path is None``)
        wird ein leerer Ein-Frame-Fallback ``{"frames":1,"fps":60}`` direkt
        eingetragen (kein Bildzugriff). Bei gesetztem, aber nicht existentem
        Pfad wird ein Fehler geloggt und derselbe Fallback verwendet.
        """
        def get_gif_info(gif_path):
            frame_count = 1
            fps = 60
            try:
                gif = Image.open(gif_path)
                fps = 1000 / gif.info.get('duration', 100)
                frame_count = gif.n_frames
                self.logger.debug(f"Vorgeladen: {gif_path}, Frames: {frame_count}, FPS: {fps}")
            except Exception as e:
                # Gesetzter, aber nicht ladbarer Pfad: Error (nicht Warning),
                # Overlay laeuft mit leerer Ein-Frame-Animation transparent
                # weiter statt zu crashen.
                self.logger.error(f"Fehler beim GIF-Scan: {e}")
            return {"frames": frame_count, "fps": fps}

        if self.idle_gif_path is None:
            # Kein idle gesetzt: leerer Ein-Frame-Fallback ohne Bildzugriff.
            self.preloaded_animations["idle"] = {"frames": 1, "fps": 60}
        else:
            self.preloaded_animations["idle"] = get_gif_info(self.idle_gif_path)
        for name, path in self.animations.items():
            self.preloaded_animations[name] = get_gif_info(path)

    def load_gif(self, gif_path, data=None):
        """Bereitet die nächste Animation vor, ohne die aktuelle zu unterbrechen.

        Setzt ``next_*``-Felder konsistent und hält das ``loading_next``-Flag in
        *jedem* Zweig auf einem definierten Wert: ``True`` für reguläre
        Animationen (Mid-Animation-Sperre), ``False`` für Idle/Fallback (die
        Sperre wird aufgehoben, sobald ein Wechsel zu Idle/Fallback geplant ist).
        """
        animation_name = "idle" if gif_path == self.idle_gif_path else next(
            (key for key, value in self.animations.items() if value == gif_path), None
        )
        # idle_gif_path is None (no idle set): treat any explicit idle-load
        # request as the empty fallback so update() does not KeyError.
        if gif_path is None and self.idle_gif_path is None:
            animation_name = "idle"
        if animation_name and animation_name == "idle":
            self.logger.debug("Laden von Idle, eindeutiger Text)")

            self.next_frames = self.preloaded_animations[animation_name]["frames"]
            self.next_fps = self.preloaded_animations[animation_name]["fps"]
            self.next_animation_name = animation_name
            self.loading_next = False  # Setze das Flag zurück

        elif animation_name and animation_name in self.preloaded_animations:
            # Lade die nächste Animation in den Zwischenspeicher
            self.loading_next = True
            self.next_frames = self.preloaded_animations[animation_name]["frames"]
            self.next_fps = self.preloaded_animations[animation_name]["fps"]
            self.next_animation_name = animation_name
        else:
            # Fallback auf Idle-Animation
            self.logger.debug(f"Warnung: Animation {gif_path} nicht vorab geladen. Fallback auf Idle.")
            self.next_frames = self.preloaded_animations["idle"]["frames"]
            self.next_fps = self.preloaded_animations["idle"]["fps"]
            self.next_animation_name = "idle"
            self.loading_next = False  # Setze das Flag zurück

        self.next_animation_data = data or {}

        self.logger.debug(f"Vorbereite nächste Animation: {self.next_animation_name}, Frames: {(self.next_frames)}, FPS: {self.next_fps}")


    def _consume_next_from_queue(self):
        """Holt genau ein Animationselement aus ``self.queue`` und plant es vor.

        Wird sowohl am Ende der aktuellen Animation als auch während einer
        laufenden Animation (sofern nicht ``loading_next``) aufgerufen —
        einheitliche Logik statt zweier duplizierter Pfade. Ungültige
        Animationen fallen auf Idle zurück; dabei wird ``loading_next``
        konsistent zurückgesetzt.
        """
        next_item = self.queue.get()
        if not isinstance(next_item, dict):
            self.logger.debug(f"Kein dict in der Queue: {next_item}")
            return
        next_animation = next_item.get("animation")
        animation_data = next_item.get("data", {})

        self.logger.debug(f"Lade nächste Animation: {next_animation}")
        if next_animation in self.animations:
            self.load_gif(self.animations[next_animation], data=animation_data)
        else:
            self.logger.debug(f"Animation nicht vorab geladen: {next_animation} -> Fallback Idle")
            self.load_gif(self.idle_gif_path)
            self.loading_next = False  # Setze das Flag zurück
        self.logger.debug(
            f"Lade next_Animation: {self.next_animation_name}, "
            f"Frames: {self.next_frames}, FPS: {self.next_fps}; "
            f"current_Animation: {self.current_animation_name}, "
            f"Frames: {self.current_frame}, FPS: {self.fps}"
        )
        self._log_queue_debug()

    def _log_queue_debug(self):
        """Gibt die Queue nur bei aktivem DEBUG-Level aus (kein Flooding).

        Vermeidet das frühere Verhalten, bei dem ``debug_queue`` auf jedem
        ``update``-Zyklus die gesamte Queue entleerte und neu befüllte (nicht
        threadsicher + Log-Flut). Jetzt nur noch, wenn DEBUG wirklich aktiv ist.
        """
        from twitchbot_runtime.logger import Severity
        if self.logger.is_enabled(Severity.DEBUG):
            self.logger.debug(f"Queue: {debug_queue(self.queue)}")

    def update(self):
        """Aktualisiert die Animation basierend auf der internen Queue.

        Zwei Auslöser für einen Queue-Konsum:
        1. Aktuelle Animation am Ende (``current_frame >= frames-1``): Wechsel
           zu ``next_animation``, dann ein weiteres Item holen, um die *nächste*
           nächste vorzubereiten.
        2. Mid-Animation, Queue nicht leer und nicht ``loading_next``:下一
           Animation vorbereiten, ohne die aktuelle zu unterbrechen.
        Beide Pfade laufen über :meth:`_consume_next_from_queue` (vereinheitlicht).
        """
        if time.time() - self.last_frame_time > 1 / self.fps:
            self.last_frame_time = time.time()

            # Wenn die aktuelle Animation vorbei ist, prüfe die Queue
            if self.current_frame >= self.frames-1:
                self.current_frame = 1

                self.current_animation_name = self.next_animation_name
                self.next_animation_name = None
                self.animation_data = self.next_animation_data
                self.next_animation_data = None
                self.frames = self.next_frames
                self.fps = self.next_fps

                if not self.queue.empty():
                    self._consume_next_from_queue()
                else:
                    self.load_gif(self.idle_gif_path)  # Lade Idle-Animation nach dem Wechsel

                self.logger.debug(f"Animation gewechselt: {self.current_animation_name}")
                self.logger.debug(f"Lade next_Animation: {self.next_animation_name}, Frames: {(self.next_frames)}, FPS: {self.next_fps}")

            elif not self.queue.empty() and not self.loading_next:
                self._consume_next_from_queue()

            self.logger.debug(f"Aktuelle Animation: {self.current_animation_name}, Frames: {self.current_frame}/{(self.frames)}, FPS: {self.fps}  nächte Animation: {self.next_animation_name}, Frames:{(self.next_frames)}, FPS: {self.next_fps}  {self.loading_next}")
            self.current_frame += 1

    def draw(self, x=0, y=0, scale=1):
        """Serialisiert den aktuellen Zustand für das Web-Overlay.

        ``frame`` ist der interne Frame-Index der Zustandsmaschine und wird
        weiterhin gesendet (Rückwärtskompatibilität). Der Browser-Client
        (``overlay.js``) treibt seine Anzeige-Frames jedoch lokal über
        ``requestAnimationFrame`` und ignoriert dieses Feld für die Darstellung
        — ``frame`` ist informativ/deprecated, nicht steuernd. Autoritativ
        für den Client ist ``animation`` (Animationswechsel + Reset des
        lokalen Zählers).
        """
        if not self.frames:
            self.logger.error("Keine Frames zum Zeichnen verfügbar.")
            return  None

        serialized_output = {
            "frame": self.current_frame,
            "animation": self.current_animation_name,
            "position": {"x": x, "y": y},
            "scale": scale
        }

        animation_data = self.animation_data or {}
        username = animation_data.get("username", "USER")
        # Speech bubble text + toggle are resolved by the Runtime and passed
        # in via animation_data (parent-side Stream_Pet.json read + placeholder
        # resolution). Fall back to self.config only for older messages that
        # predate the runtime-side path (e.g. queued before restart). The bubble
        # is gated purely by toggle + text, independent of the animation name.
        toggle = animation_data.get("speech_bubble_toggle")
        if toggle is None:
            toggle = self.config.get("speech_bubble_toggle", False)
        speech_text = animation_data.get("speech_bubble_text")
        if speech_text is None:
            speech_text = self.config.get("speech_bubble_text")
        spc = self.config.get("stream_pet_config", {})
        if not toggle or not speech_text:
            # speech_bubble_text/toggle missing or off: Sprechblase weglassen
            # statt KeyError zu werfen.
            serialized_output["speech_bubble"] = {
                "text": "",
                "visible": False,
                "position": {"x": 0, "y": 0},
                "font": spc.get("font", "Arial"),
                "font_size": 0
            }
        else:
            # animation_data["speech_bubble_text"] ist bereits runtime-seitig
            # aufgelöst; nur noch defensiv {username} ersetzen, falls der Text
            # aus dem Config-Fallback (ungeklärt) stammt.
            text = speech_text.replace("{username}", username)

            # Berechne Bubble-Position (wir zeichnen sie nicht bei serialize, sondern geben Koordinaten und Text zurück)
            font_size = int(spc.get("text_size", 12) * scale)

            bubble_pos = spc.get("speech_bubble_position", {"x": 0, "y": 0})
            bubble_x = int(x + bubble_pos.get("x", 0) * scale)
            bubble_y = int(y + bubble_pos.get("y", 0) * scale)

            serialized_output["speech_bubble"] = {
                "text": text,
                "visible": True,
                "position": {"x": bubble_x, "y": bubble_y},
                "font": spc.get("font", "Arial"),
                "font_size": font_size
            }

        return serialized_output

    def add_animation(self, animation_name, extra_data=None):
        """Fügt eine Animation zur internen Queue hinzu (Datenkanal)."""
        self.queue.put({
            "animation": animation_name,
            "data": extra_data or {}
        })
        self.logger.info(f"Animation zur Queue hinzugefügt: {animation_name} mit Daten: {extra_data}")
        self._log_queue_debug()

def debug_queue(queue):
    """Gibt die Inhalte der Queue aus, ohne sie zu verändern."""
    temp_list = []
    while not queue.empty():
        item = queue.get()
        temp_list.append(item)
    # Füge die Elemente zurück in die Queue
    for item in temp_list:
        queue.put(item)
    return temp_list
