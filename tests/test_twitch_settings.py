import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.twitch_settings import (
    BOT_REQUIRED_KEYS,
    BOT_SCOPES,
    CHANNEL_SCOPES,
    TwitchSettings,
    parse_env_text,
    serialize_env,
)


def test_parse_env_text_handles_comments_quotes_and_blanks():
    text = """
# bot credentials
BOT_CLIENT_ID="abc123"
BOT_CLIENT_SECRET='secret with spaces'
BOT_USERNAME=botuser

TWITCH_CHANNEL=somestreamer
"""
    parsed = parse_env_text(text)

    assert parsed == {
        "BOT_CLIENT_ID": "abc123",
        "BOT_CLIENT_SECRET": "secret with spaces",
        "BOT_USERNAME": "botuser",
        "TWITCH_CHANNEL": "somestreamer",
    }


def test_parse_env_text_ignores_lines_without_equals():
    text = "INVALID_LINE\nBOT_CLIENT_ID=ok\n"
    parsed = parse_env_text(text)

    assert parsed == {"BOT_CLIENT_ID": "ok"}


def test_serialize_env_round_trips(tmp_path):
    mapping = {"BOT_CLIENT_ID": "abc", "TWITCH_CHANNEL": "streamer", "EMPTY": ""}
    serialized = serialize_env(mapping)

    assert "BOT_CLIENT_ID=abc" in serialized
    assert "TWITCH_CHANNEL=streamer" in serialized
    assert "EMPTY=" in serialized

    assert parse_env_text(serialized) == mapping


def test_load_reads_existing_env_file(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("BOT_CLIENT_ID=cid\nBOT_USERNAME=bot\nTWITCH_CHANNEL=chan\n", encoding="utf-8")

    settings = TwitchSettings.load(env_path)

    assert settings.bot_client_id == "cid"
    assert settings.bot_username == "bot"
    assert settings.twitch_channel == "chan"


def test_load_missing_file_returns_empty_settings(tmp_path):
    settings = TwitchSettings.load(tmp_path / "missing.env")

    assert settings.bot_client_id == ""
    assert settings.missing_bot_keys() == list(BOT_REQUIRED_KEYS)


def test_write_env_creates_and_updates_file(tmp_path):
    env_path = tmp_path / ".env"
    settings = TwitchSettings(env_path)
    settings.write_env({"BOT_CLIENT_ID": "cid", "BOT_USERNAME": "bot"})

    assert env_path.exists()
    assert "BOT_CLIENT_ID=cid" in env_path.read_text(encoding="utf-8")

    settings.write_env({"TWITCH_CHANNEL": "chan"})

    text = env_path.read_text(encoding="utf-8")
    assert "BOT_CLIENT_ID=cid" in text
    assert "TWITCH_CHANNEL=chan" in text


def test_missing_bot_keys_lists_only_empty_required_keys(tmp_path):
    settings = TwitchSettings(tmp_path / ".env")
    settings.write_env({"BOT_CLIENT_ID": "cid", "BOT_USERNAME": "bot"})

    missing = settings.missing_bot_keys()

    assert missing == ["BOT_CLIENT_SECRET", "TWITCH_CHANNEL"]


def test_is_complete_true_when_all_bot_required_keys_present(tmp_path):
    settings = TwitchSettings(tmp_path / ".env")
    settings.write_env({
        "BOT_CLIENT_ID": "cid",
        "BOT_CLIENT_SECRET": "csecret",
        "BOT_USERNAME": "bot",
        "TWITCH_CHANNEL": "chan",
    })

    assert settings.is_complete() is True


def test_channel_client_id_falls_back_to_bot_client_id(tmp_path):
    settings = TwitchSettings(tmp_path / ".env")
    settings.write_env({"BOT_CLIENT_ID": "shared-cid"})

    assert settings.channel_client_id == "shared-cid"

    settings.write_env({"CHANNEL_CLIENT_ID": "channel-cid"})
    settings.reload()

    assert settings.channel_client_id == "channel-cid"


def test_bot_scopes_present_parses_scopes_field(tmp_path):
    settings = TwitchSettings(tmp_path / ".env")
    settings.write_env({"BOT_SCOPES": "user:read:chat user:bot  clips:edit"})

    present = settings.bot_scopes_present()

    assert "user:read:chat" in present
    assert "user:bot" in present
    assert "clips:edit" in present
    assert "moderator:manage:banned_users" not in present


def test_bot_scopes_missing_lists_unset_scopes(tmp_path):
    settings = TwitchSettings(tmp_path / ".env")
    settings.write_env({"BOT_SCOPES": "user:read:chat"})

    missing = settings.bot_scopes_missing()

    assert "user:write:chat" in missing
    assert "user:read:chat" not in missing
    assert set(missing) <= set(BOT_SCOPES)


def test_channel_scopes_missing_lists_unset_scopes(tmp_path):
    settings = TwitchSettings(tmp_path / ".env")

    missing = settings.channel_scopes_missing()

    assert set(missing) == set(CHANNEL_SCOPES)
