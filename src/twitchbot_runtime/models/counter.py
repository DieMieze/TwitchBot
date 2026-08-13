from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Counter:
    """Persistent counter value with optional subcounters and an active selection."""

    name: str
    category: str = "default"
    value: int = 0
    subcounters: dict[str, dict] = field(default_factory=dict)
    active_subcounter: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    @property
    def key(self) -> str:
        return f"{self.name}:{self.category}"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "value": self.value,
            "subcounters": self.subcounters,
            "active_subcounter": self.active_subcounter,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Counter:
        return cls(
            name=data.get("name", ""),
            category=data.get("category", "default"),
            value=data.get("value", 0),
            subcounters=dict(data.get("subcounters", {}) or {}),
            active_subcounter=data.get("active_subcounter"),
            created_at=data.get("created_at", ""),
        )
