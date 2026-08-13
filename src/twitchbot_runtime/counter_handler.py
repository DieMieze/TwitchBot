from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models.counter import Counter


class CounterHandler:
    """Manages persistent counters with value, subcounter, and placeholder support."""

    def __init__(self, store_path: str | Path = "counters.json") -> None:
        """
        @brief Construct a CounterHandler and load persisted counters.

        @param store_path: path to the JSON file counters are persisted to
            (keyed ``"name:category"``). Defaults to ``counters.json``.
        @return: None
        """
        self.store_path = Path(store_path)
        self.counters: dict[str, Counter] = {}
        self._load()

    def handle(self, action: str, payload: dict) -> dict:
        """
        @brief Dispatch a counter action by name to its ``_action_<name>`` method.

        @param action: counter action (increment/decrement/set/reset/create/
            delete/add_subcounter/select_subcounter/clear_active_subcounter/
            delete_subcounter/query).
        @param payload: action payload dict (must include ``name`` for most
            actions; see each ``_action_*`` method for required keys).
        @return: the action result dict, or ``{"error": "unknown_action"}``
            when the action is not recognized.
        """
        method = getattr(self, f"_action_{action}", None)
        if method is None:
            return {"error": "unknown_action", "action": action}
        return method(payload)

    def _resolve(self, payload: dict) -> Counter | None:
        name = payload.get("name")
        if not name:
            return None
        category = payload.get("category", "default")
        key = f"{name}:{category}"
        return self.counters.get(key)

    def _ensure_counter(self, payload: dict) -> Counter | None:
        """Resolve the counter for ``payload`` or auto-create it.

        Used by mutating/query actions to implement "auto-create on first
        use": when no matching counter exists, a fresh ``Counter(name,
        category)`` (value 0) is created and persisted. Returns ``None`` when
        ``payload`` has no ``name``. ``delete`` and ``create`` keep using
        :meth:`_resolve` (no auto-create).
        """
        name = payload.get("name")
        if not name:
            return None
        category = payload.get("category", "default")
        key = f"{name}:{category}"
        counter = self.counters.get(key)
        if counter is None:
            counter = Counter(name=name, category=category)
            self.counters[key] = counter
            self._save()
        return counter

    @staticmethod
    def _coerce_int(value: Any, fallback: int) -> int:
        """Best-effort ``int`` coercion preserving existing int inputs."""
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return fallback

    def _active_subcounter(self, counter: Counter) -> dict | None:
        name = counter.active_subcounter
        if not name:
            return None
        sub = counter.subcounters.get(name)
        if sub is None:
            counter.active_subcounter = None
            return None
        return sub

    def _action_increment(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        amount = self._coerce_int(payload.get("amount", 1), 1)
        counter.value += amount
        sub = self._active_subcounter(counter)
        target = "counter"
        sub_value = None
        if sub is not None:
            sub["value"] = int(sub.get("value", 0)) + amount
            sub_value = sub["value"]
            target = "both"
        self._save()
        return {
            "action": "increment",
            "key": counter.key,
            "value": counter.value,
            "active_subcounter": counter.active_subcounter,
            "subcounter_value": sub_value,
            "target": target,
        }

    def _action_decrement(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        amount = self._coerce_int(payload.get("amount", 1), 1)
        counter.value -= amount
        sub = self._active_subcounter(counter)
        target = "counter"
        sub_value = None
        if sub is not None:
            sub["value"] = int(sub.get("value", 0)) - amount
            sub_value = sub["value"]
            target = "both"
        self._save()
        return {
            "action": "decrement",
            "key": counter.key,
            "value": counter.value,
            "active_subcounter": counter.active_subcounter,
            "subcounter_value": sub_value,
            "target": target,
        }

    def _action_set(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        value = self._coerce_int(payload.get("value", 0), 0)
        sub = self._active_subcounter(counter)
        sub_value = None
        if sub is not None:
            sub["value"] = value
            target = "subcounter"
            sub_value = sub["value"]
        else:
            counter.value = value
            target = "counter"
        self._save()
        return {
            "action": "set",
            "key": counter.key,
            "value": counter.value,
            "active_subcounter": counter.active_subcounter,
            "subcounter_value": sub_value,
            "target": target,
        }

    def _action_reset(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        sub = self._active_subcounter(counter)
        sub_value = None
        if sub is not None:
            sub["value"] = 0
            target = "subcounter"
            sub_value = sub["value"]
        else:
            counter.value = 0
            target = "counter"
        self._save()
        return {
            "action": "reset",
            "key": counter.key,
            "value": counter.value,
            "active_subcounter": counter.active_subcounter,
            "subcounter_value": sub_value,
            "target": target,
        }

    def _action_create(self, payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            return {"error": "missing_name"}
        category = payload.get("category", "default")
        key = f"{name}:{category}"
        if key in self.counters:
            return {"error": "counter_exists", "name": name, "category": category}
        counter = Counter(name=name, category=category)
        self.counters[key] = counter
        self._save()
        return {"action": "create", "key": counter.key, "counter": counter.to_dict()}

    def _action_delete(self, payload: dict) -> dict:
        name = payload.get("name")
        if not name:
            return {"error": "missing_name"}
        category = payload.get("category", "default")
        key = f"{name}:{category}"
        if key not in self.counters:
            return {"error": "counter_not_found", "name": name, "category": category}
        del self.counters[key]
        self._save()
        return {"action": "delete", "key": key, "deleted": True}

    def _action_add_subcounter(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        sub_name = payload.get("subcounter_name")
        if not sub_name:
            return {"error": "missing_subcounter_name"}
        counter.subcounters[sub_name] = {"name": sub_name, "value": 0}
        self._save()
        return {
            "action": "add_subcounter",
            "key": counter.key,
            "subcounter": sub_name,
            "subcounters": counter.subcounters,
        }

    def _action_select_subcounter(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        sub_name = payload.get("subcounter_name")
        if sub_name is None:
            return {"error": "missing_subcounter_name"}
        if sub_name not in counter.subcounters and sub_name != "":
            return {"error": "subcounter_not_found", "subcounter": sub_name}
        counter.active_subcounter = sub_name
        self._save()
        return {
            "action": "select_subcounter",
            "key": counter.key,
            "active_subcounter": counter.active_subcounter,
        }

    def _action_clear_active_subcounter(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        counter.active_subcounter = None
        self._save()
        return {"action": "clear_active_subcounter", "key": counter.key, "active_subcounter": None}

    def _action_delete_subcounter(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        sub_name = payload.get("subcounter_name")
        if not sub_name:
            return {"error": "missing_subcounter_name"}
        if sub_name not in counter.subcounters:
            return {"error": "subcounter_not_found", "subcounter": sub_name}
        del counter.subcounters[sub_name]
        if counter.active_subcounter == sub_name:
            counter.active_subcounter = None
        self._save()
        return {
            "action": "delete_subcounter",
            "key": counter.key,
            "subcounter": sub_name,
            "subcounters": counter.subcounters,
        }

    def _action_query(self, payload: dict) -> dict:
        counter = self._ensure_counter(payload)
        if counter is None:
            return {"error": "missing_name"}
        active = None
        if counter.active_subcounter:
            active = counter.subcounters.get(counter.active_subcounter)
        return {
            "action": "query",
            "key": counter.key,
            "value": counter.value,
            "active_subcounter": counter.active_subcounter,
            "active_subcounter_value": active.get("value") if active else None,
            "subcounters": counter.subcounters,
        }

    def replace_placeholders(self, message: str, counter: Counter) -> str:
        """
        @brief Substitute ``{counter:name:field}`` placeholders for a specific counter.

        Only placeholders whose ``name`` matches the given counter are
        substituted; others are left intact. Used when a single counter is
        in context.

        @param message: the message potentially containing counter placeholders.
        @param counter: the Counter whose fields fill matching placeholders.
        @return: the message with the counter's placeholders substituted.
        """
        return self._substitute_counter(message, counter)

    def resolve_placeholders(self, message: str) -> str:
        """Resolve all ``{counter:name:field}`` placeholders in ``message``.

        Each placeholder is resolved against the first stored counter whose
        name matches. Unknown counters are left untouched.
        """
        pattern = re.compile(r"\{counter:(?P<name>[^:}]+):(?P<field>[^}]+)\}")

        def _replace(match: re.Match[str]) -> str:
            name = match.group("name")
            counter = self._find_counter_by_name(name)
            if counter is None:
                return match.group(0)
            return self._format_field(match.group("field"), counter)

        return pattern.sub(_replace, message)

    def _find_counter_by_name(self, name: str) -> Counter | None:
        for counter in self.counters.values():
            if counter.name == name:
                return counter
        return None

    def _substitute_counter(self, message: str, counter: Counter) -> str:
        pattern = re.compile(r"\{counter:(?P<name>[^:}]+):(?P<field>[^}]+)\}")

        def _replace(match: re.Match[str]) -> str:
            name = match.group("name")
            if name != counter.name:
                return match.group(0)
            return self._format_field(match.group("field"), counter)

        return pattern.sub(_replace, message)

    def _format_field(self, field_name: str, counter: Counter) -> str:
        if field_name == "name":
            return str(counter.name)
        if field_name == "value":
            return str(counter.value)
        if field_name == "subcounter_value":
            if counter.active_subcounter:
                sub = counter.subcounters.get(counter.active_subcounter)
                if sub is not None:
                    return str(sub.get("value", 0))
            return "0"
        if field_name == "subcounter_label":
            if counter.active_subcounter:
                sub = counter.subcounters.get(counter.active_subcounter)
                if sub is not None:
                    try:
                        sub_val = int(sub.get("value", 0))
                    except (TypeError, ValueError):
                        sub_val = 0
                    return f" ({counter.active_subcounter}: {sub_val})"
            return ""
        return f"{{counter:{counter.name}:{field_name}}}"

    def _load(self) -> None:
        if not self.store_path.exists():
            self.counters = {}
            return
        try:
            with self.store_path.open("r", encoding="utf-8") as handle:
                data: dict[str, Any] = json.load(handle)
        except (json.JSONDecodeError, OSError):
            self.counters = {}
            return
        self.counters = {key: Counter.from_dict(entry) for key, entry in data.items()}

    def _save(self) -> None:
        payload = {counter.key: counter.to_dict() for counter in self.counters.values()}
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.store_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=4)
