from __future__ import annotations

import copy
import json
from typing import Any

from pydantic import BaseModel

from twitchbot_runtime.schemas import CommandSchema, CommandsDocument


def _resolve_refs(node: Any, root: dict[str, Any], _visiting: set[str] | None = None) -> Any:
    visiting = _visiting or set()
    if isinstance(node, dict):
        if "$ref" in node:
            ref_path = node["$ref"]
            if ref_path.startswith("#/"):
                if ref_path in visiting:
                    # Recursive self-reference: leave the $ref in place so the
                    # inlined schema stays finite (the $defs block is kept).
                    return {"$ref": ref_path}
                target = root
                for part in ref_path[2:].split("/"):
                    target = target.get(part, {})
                return _resolve_refs(copy.deepcopy(target), root, visiting | {ref_path})
            return node
        resolved: dict[str, Any] = {}
        for key, value in node.items():
            resolved[key] = _resolve_refs(value, root, visiting)
        return resolved
    if isinstance(node, list):
        return [_resolve_refs(item, root, visiting) for item in node]
    return node


def _resolve_anyof(node: Any) -> Any:
    if isinstance(node, dict):
        if "anyOf" in node and isinstance(node["anyOf"], list):
            non_null = [
                opt for opt in node["anyOf"]
                if not (isinstance(opt, dict) and opt.get("type") == "null")
            ]
            if non_null:
                merged = {k: v for k, v in node.items() if k != "anyOf"}
                for opt in non_null:
                    if isinstance(opt, dict):
                        merged.update(opt)
                node = merged
        return {k: _resolve_anyof(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_anyof(item) for item in node]
    return node


def _inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    resolved = _resolve_refs(raw, raw)
    resolved = _resolve_anyof(resolved)
    resolved.pop("title", None)
    return resolved


def build_config_schema() -> dict[str, Any]:
    schema = _inline_schema(CommandsDocument)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "TwitchBotCommandsConfig"
    return schema


def build_command_schema() -> dict[str, Any]:
    schema = _inline_schema(CommandSchema)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["title"] = "TwitchBotCommand"
    return schema


def dump_config_schema(indent: int | None = 2) -> str:
    return json.dumps(build_config_schema(), indent=indent, ensure_ascii=False)


def build_config_schema_message() -> dict[str, Any]:
    return {
        "type": "config_schema",
        "schema": build_config_schema(),
        "command_schema": build_command_schema(),
    }
