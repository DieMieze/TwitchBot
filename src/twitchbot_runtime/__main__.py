from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import TwitchBot, load_settings
from .mode import Mode
from .test_repl import ReplSession, replay_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the TwitchBot runtime in a configurable execution mode."
    )
    parser.add_argument(
        "--settings-path",
        "-s",
        default="settings.json",
        help="Path to the runtime settings JSON file.",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["test", "silent", "production"],
        help="Override the execution mode defined in settings.",
    )
    parser.add_argument(
        "--test-file",
        default=None,
        help="Path to a JSONL file to replay in test mode.",
    )
    parser.add_argument(
        "--show-settings",
        action="store_true",
        help="Print the effective settings and exit without starting the bot.",
    )

    args = parser.parse_args()
    settings_path = Path(args.settings_path)

    if args.show_settings:
        settings = load_settings(settings_path)
        if args.mode:
            settings.setdefault("runtime", {})["execution_mode"] = args.mode
        print(json.dumps(settings, indent=2, ensure_ascii=False))
        return 0

    bot = TwitchBot(settings_path=settings_path, execution_mode=args.mode)

    print("Starting TwitchBot runtime")
    print(f"execution_mode={bot.mode.value}")
    print(f"settings_path={settings_path}")
    print("Available features:", ", ".join(bot.settings.get("features", {}).keys()))

    twitch_obj = getattr(bot, "_twitch_settings_obj", None)
    if bot.mode is not Mode.TEST and twitch_obj is not None:
        if hasattr(twitch_obj, "is_complete") and twitch_obj.is_complete():
            print(f"Twitch credentials: bot={twitch_obj.bot_username} channel={twitch_obj.twitch_channel}")
        else:
            missing: list[str] = getattr(twitch_obj, "missing_bot_keys", lambda: [])()
            print(f"Twitch credentials incomplete (missing: {', '.join(missing) or 'n/a'})")
            print("Run: python scripts/get_all_scopes.py")

    if bot.mode is not Mode.TEST:
        tunnel = getattr(bot, "_tunnel_manager", None)
        public_url: str = getattr(tunnel, "public_url", "") if tunnel is not None else ""
        if public_url:
            print(f"Tunnel URL: {public_url}")

    if bot.mode is Mode.TEST:
        if args.test_file:
            results = replay_file(bot, args.test_file)
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            ReplSession(bot).run()
    else:
        bot.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
