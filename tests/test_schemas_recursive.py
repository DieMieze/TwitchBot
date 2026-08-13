import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.config_schema import build_command_schema, build_config_schema
from twitchbot_runtime.schemas import CommandSchema, empty_command


def test_empty_command_has_when_and_reactions_root():
    cmd = empty_command()
    assert cmd["name"] == "New command"
    assert cmd["when"]["kind"] == "and"
    assert cmd["when"]["children"][0]["kind"] == "leaf"
    assert cmd["when"]["children"][0]["condition"]["type"] == "command"
    assert cmd["when"]["children"][0]["condition"]["command"] == "!new_command"
    assert cmd["reactions"]["kind"] == "seq"
    assert cmd["reactions"]["children"] == []


def test_command_schema_validates_nested_when_tree():
    payload = {
        "name": "so",
        "when": {
            "kind": "and",
            "children": [
                {"kind": "leaf", "condition": {"type": "command", "command": "!so"}},
                {
                    "kind": "not",
                    "child": {"kind": "leaf", "condition": {"type": "cheer", "min_bits": 100}},
                },
                {
                    "kind": "leaf",
                    "condition": {
                        "type": "compare",
                        "field": "{counter:deaths:value}",
                        "op": ">=",
                        "value": 5,
                    },
                },
            ],
        },
        "roles": [],
        "reactions": {
            "kind": "seq",
            "children": [
                {
                    "kind": "if",
                    "when": {"kind": "leaf", "condition": {"type": "follow"}},
                    "then": {
                        "kind": "reaction",
                        "reaction": {"type": "chat_reply", "message": "Welcome!"},
                    },
                    "else": {
                        "kind": "reaction",
                        "reaction": {"type": "overlay_text", "text": "no follow"},
                    },
                },
                {
                    "kind": "switch",
                    "on": "{args[0]}",
                    "cases": [
                        {
                            "equals": "red",
                            "then": {
                                "kind": "reaction",
                                "reaction": {"type": "overlay_gif", "gif_id": "red"},
                            },
                        }
                    ],
                    "default": {
                        "kind": "reaction",
                        "reaction": {"type": "chat_reply", "message": "unknown"},
                    },
                },
            ],
        },
    }
    model = CommandSchema.model_validate(payload)
    assert model.name == "so"
    dumped = model.model_dump(by_alias=True)
    assert dumped["when"]["kind"] == "and"
    assert dumped["reactions"]["kind"] == "seq"
    assert dumped["reactions"]["children"][0]["kind"] == "if"
    assert "else" in dumped["reactions"]["children"][0]


def test_command_schema_accepts_all_alias_for_and():
    payload = {
        "name": "alias",
        "when": {"kind": "all", "children": []},
        "reactions": {"kind": "seq", "children": []},
    }
    model = CommandSchema.model_validate(payload)
    assert model.when.kind in ("and", "all")


def test_build_config_schema_has_commands_property():
    schema = build_config_schema()
    assert schema["type"] == "object"
    assert "commands" in schema["properties"]


def test_build_command_schema_has_when_and_reactions():
    schema = build_command_schema()
    props = schema["properties"]
    assert "when" in props
    assert "reactions" in props
    assert "name" in props
