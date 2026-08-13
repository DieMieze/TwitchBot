from __future__ import annotations

import re
from typing import Any

_COMPARE_OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "contains", "regex"}


def _coerce_pair(left: Any, right: Any) -> tuple[Any, Any]:
    """Best-effort numeric coercion for comparison (mirrors cheer/raid int coercion)."""
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left, right
    if isinstance(left, bool) or isinstance(right, bool):
        return left, right
    try:
        if isinstance(left, str) and isinstance(right, (int, float)):
            return float(left), float(right)
        if isinstance(right, str) and isinstance(left, (int, float)):
            return float(left), float(right)
        if isinstance(left, str) and isinstance(right, str):
            try:
                lf = float(left)
                rf = float(right)
                return lf, rf
            except (TypeError, ValueError):
                return left, right
    except (TypeError, ValueError):
        return left, right
    return left, right


def evaluate_compare(field: str, op: str, value: Any, resolve_placeholder: Any) -> bool:
    """Evaluate a ``compare`` leaf: ``field <op> value``.

    ``field`` is first run through the ``resolve_placeholder`` callable so that
    ``{counter:...}``/``{args[N]}``/``{username}``/``{target}`` resolve before
    comparison. Unknown operators return ``False``.
    """
    if op not in _COMPARE_OPS:
        return False

    if callable(resolve_placeholder):
        try:
            field = resolve_placeholder(field)
        except Exception:
            field = field

    if op == "regex":
        try:
            return re.search(str(value), str(field)) is not None
        except re.error:
            return False

    if op == "in":
        try:
            return field in value
        except TypeError:
            return False

    if op == "contains":
        try:
            return value in field
        except TypeError:
            return False

    left, right = _coerce_pair(field, value)

    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
    except TypeError:
        return False

    return False
