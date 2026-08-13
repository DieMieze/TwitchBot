from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    TEST = "test"
    SILENT = "silent"
    PRODUCTION = "production"

    @staticmethod
    def from_string(value: str) -> Mode:
        legacy = {"bot": Mode.PRODUCTION, "log_only": Mode.SILENT}
        if value in legacy:
            return legacy[value]
        try:
            return Mode(value)
        except ValueError:
            return Mode.TEST


def is_live(mode: Mode) -> bool:
    return mode is Mode.PRODUCTION
