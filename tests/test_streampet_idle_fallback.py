import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest

pytest.importorskip("PIL")

from Overlay_project.StreamPet import StreamPet


class DummyLogger:
    """Minimal logger stub matching the StreamPet logger interface."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.debugs = []
        self.infos = []

    def error(self, message, *args):
        self.errors.append(message)

    def warning(self, message, *args):
        self.warnings.append(message)

    def warn(self, message, *args):
        self.warnings.append(message)

    def debug(self, message, *args):
        self.debugs.append(message)

    def info(self, message, *args):
        self.infos.append(message)

    def is_enabled(self, severity):
        return False


def test_idle_none_uses_empty_one_frame_fallback():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    # Invariant: idle exists with the empty fallback, no image access.
    assert pet.preloaded_animations["idle"] == {"frames": 1, "fps": 60}
    assert pet.idle_gif_path is None
    # __init__ follow-up lines did not crash -> next_frames/fps set.
    assert pet.frames == 1
    assert pet.fps == 60


def test_empty_string_idle_treated_as_none():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path="", animations={}, overlay_logger=logger)
    assert pet.idle_gif_path is None
    assert pet.preloaded_animations["idle"] == {"frames": 1, "fps": 60}


def test_broken_idle_path_logs_error_and_falls_back():
    logger = DummyLogger()
    pet = StreamPet(
        idle_gif_path="StreamPet/does_not_exist.gif",
        animations={},
        overlay_logger=logger,
    )
    # Broken path -> error logged (not warning) and a 1-frame fallback.
    assert len(logger.errors) >= 1
    assert pet.preloaded_animations["idle"]["frames"] == 1
    assert pet.preloaded_animations["idle"]["fps"] == 60


def test_draw_in_idle_state_no_keyerror_on_empty_config(tmp_path, monkeypatch):
    # Empty config (missing Stream_Pet.json): StreamPet.__init__ already sets
    # self.config = {} on file load failure. Simulate by pointing config_path
    # at a non-existent file inside the project layout.
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    pet.config = {}  # force empty (as if file missing)
    pet.current_animation_name = "idle"
    pet.animation_data = None
    out = pet.draw(x=10, y=20, scale=1)
    # No KeyError, speech bubble invisible (toggle defaults False).
    assert out is not None
    assert out["speech_bubble"]["visible"] is False


def test_draw_wave_branch_no_keyerror_on_empty_config():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    pet.config = {"speech_bubble_toggle": True}  # toggle on but no text/config
    pet.current_animation_name = "wave"
    pet.animation_data = {"username": "Bob"}
    out = pet.draw(x=0, y=0, scale=1)
    # speech_bubble_text missing -> invisible bubble, no KeyError.
    assert out["speech_bubble"]["visible"] is False
    assert out["speech_bubble"]["text"] == ""


def test_draw_wave_branch_with_full_config():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    pet.config = {
        "speech_bubble_toggle": True,
        "speech_bubble_text": "Hi {username}",
        "stream_pet_config": {
            "text_size": 12,
            "font": "Comic",
            "speech_bubble_position": {"x": 10, "y": -5},
        },
    }
    pet.current_animation_name = "wave"
    pet.animation_data = {"username": "Bob"}
    out = pet.draw(x=100, y=200, scale=2)
    assert out["speech_bubble"]["visible"] is True
    assert out["speech_bubble"]["text"] == "Hi Bob"
    assert out["speech_bubble"]["font"] == "Comic"
    assert out["speech_bubble"]["position"]["x"] == 100 + 10 * 2
    assert out["speech_bubble"]["position"]["y"] == 200 + (-5) * 2


def test_draw_wave_consumes_runtime_resolved_speech_bubble_from_animation_data():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    pet.config = {
        "speech_bubble_toggle": False,  # config toggle off; animation_data overrides
        "speech_bubble_text": "OLD CONFIG TEXT",  # should NOT be used
        "stream_pet_config": {"text_size": 12, "font": "Arial"},
    }
    pet.current_animation_name = "wave"
    pet.animation_data = {
        "username": "Bob",
        "speech_bubble_text": "Hi Bob, you said hello",  # already runtime-resolved
        "speech_bubble_toggle": True,
    }
    out = pet.draw(x=0, y=0, scale=1)
    assert out["speech_bubble"]["visible"] is True
    assert out["speech_bubble"]["text"] == "Hi Bob, you said hello"


def test_draw_wave_animation_data_toggle_off_overrides_config_toggle_on():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    pet.config = {
        "speech_bubble_toggle": True,
        "speech_bubble_text": "config text",
        "stream_pet_config": {"text_size": 12, "font": "Arial"},
    }
    pet.current_animation_name = "wave"
    pet.animation_data = {"username": "Bob", "speech_bubble_toggle": False}
    out = pet.draw(x=0, y=0, scale=1)
    assert out["speech_bubble"]["visible"] is False


def test_draw_wave_falls_back_to_config_for_legacy_animation_data():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    pet.config = {
        "speech_bubble_toggle": True,
        "speech_bubble_text": "Legacy {username}",
        "stream_pet_config": {"text_size": 12, "font": "Arial"},
    }
    pet.current_animation_name = "wave"
    # legacy animation_data: no speech_bubble_text/toggle keys (pre-runtime-resolution)
    pet.animation_data = {"username": "Bob"}
    out = pet.draw(x=0, y=0, scale=1)
    assert out["speech_bubble"]["visible"] is True
    assert out["speech_bubble"]["text"] == "Legacy Bob"


def test_draw_speech_bubble_independent_of_animation_name():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    pet.config = {
        "speech_bubble_toggle": True,
        "speech_bubble_text": "Hi {username}",
        "stream_pet_config": {"text_size": 12, "font": "Arial"},
    }
    pet.current_animation_name = "dance"  # NOT wave; bubble must still show
    pet.animation_data = {"username": "Bob"}
    out = pet.draw(x=0, y=0, scale=1)
    assert out["speech_bubble"]["visible"] is True
    assert out["speech_bubble"]["text"] == "Hi Bob"


def test_draw_speech_bubble_hidden_when_toggle_off_non_wave():
    logger = DummyLogger()
    pet = StreamPet(idle_gif_path=None, animations={}, overlay_logger=logger)
    pet.config = {
        "speech_bubble_toggle": False,
        "speech_bubble_text": "Hi {username}",
        "stream_pet_config": {"text_size": 12, "font": "Arial"},
    }
    pet.current_animation_name = "dance"
    pet.animation_data = {"username": "Bob"}
    out = pet.draw(x=0, y=0, scale=1)
    assert out["speech_bubble"]["visible"] is False
