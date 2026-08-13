#!/usr/bin/env python3
"""Renew Twitch credentials (bot + channel) with the full scope set.

Standalone CLI: reads BOT_CLIENT_ID + BOT_CLIENT_SECRET from .env (or CLI
args), runs the OAuth browser flow once for the bot account (all send +
receive scopes) and once for the channel/broadcaster account (read-only
scopes), and persists both token pairs (access + refresh) into .env via
TwitchSettings.

Usage:
    python scripts/get_all_scopes.py [--bot-only | --channel-only]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from twitchbot_runtime.eventsub.oauth_flow import (  # noqa: E402
    BOT_SCOPES,
    CHANNEL_SCOPES,
    DEFAULT_OAUTH_PORT,
    OAuthFlowStarter,
)
from twitchbot_runtime.ports import resolve_port_or_exit  # noqa: E402
from twitchbot_runtime.settings import load_settings  # noqa: E402
from twitchbot_runtime.twitch_settings import TwitchSettings  # noqa: E402

SETTINGS_PATH = ROOT / "settings.json"


def _resolve_oauth_port() -> tuple[int, str]:
    """Resolve the OAuth callback port + redirect_uri from settings.json.

    Returns ``(port, redirect_uri)``. The port is resolved via
    :func:`resolve_port_or_exit` (interactive prompt on first run, persisted
    thereafter, freedom-checked). The redirect_uri is rebuilt from the port.
    A warning is printed when the port differs from the historic default
    (5003) because the Twitch Developer Console Redirect URI must match.
    """
    port = resolve_port_or_exit("oauth", load_settings(str(SETTINGS_PATH)), str(SETTINGS_PATH))
    redirect_uri = f"http://localhost:{port}/oauth/callback"
    if port != DEFAULT_OAUTH_PORT:
        print(
            f"WARNING: OAuth port is {port}, not {DEFAULT_OAUTH_PORT}. The "
            "Redirect URI in the Twitch Developer Console must be "
            f"{redirect_uri} or authorization will fail.",
            file=sys.stderr,
        )
    return port, redirect_uri


def run_for_account(
    flow: OAuthFlowStarter,
    settings: TwitchSettings,
    client_id: str,
    scopes: list[str],
    label: str,
    prefix: str,
    redirect_uri: str,
    port: int,
) -> int:
    """
    @brief Run the OAuth browser flow for a single account and persist its tokens.

    Starts the OAuth flow for the given client_id and scope set, waits for the
    user to authenticate in the browser, then writes the resulting access and
    refresh tokens into .env under the given prefix (BOT_* or CHANNEL_*).

    @param flow: OAuthFlowStarter used to run the authorize + code-exchange flow.
    @param settings: TwitchSettings wrapper used to write tokens to .env; also
        the source of the client secret (``bot_client_secret``) passed to the
        flow so the user does not have to paste it.
    @param client_id: Twitch client id to authorize against.
    @param scopes: list of OAuth scope strings to request.
    @param label: human-readable account label printed to stdout (e.g. "Bot").
    @param prefix: env-key prefix for the written tokens (e.g. "BOT"/"CHANNEL").
    @param redirect_uri: OAuth redirect URI (must match Twitch Console).
    @param port: local port for the callback server.
    @return: 0 on success, 1 when no token was returned by the flow.
    """
    print(f"\n=== {label} ===")
    print("Open the printed URL and authenticate as the", label, "account.")
    secret = settings.bot_client_secret
    result = flow.start_and_wait(client_id, scopes, redirect_uri, port=port, client_secret=secret)
    if result is None:
        print(f"{label}: no token returned; aborting.")
        return 1
    access, refresh = result
    settings.write_env({
        f"{prefix}_OAUTH_TOKEN": access,
        f"{prefix}_REFRESH_TOKEN": refresh,
    })
    print(f"{label}: tokens written to {settings.env_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """
    @brief CLI entry point that renews bot + channel OAuth credentials.

    Parses arguments, loads TwitchSettings from the configured .env, and runs
    the OAuth flow for the bot and/or channel accounts (honoring --bot-only /
    --channel-only). After writing the tokens it reloads settings and reports
    any still-missing scopes for the refreshed accounts.

    @param argv: optional argv list for argument parsing; None uses sys.argv.
    @return: process exit code (0 success, 1 flow failure, 2 missing client id).
    """
    parser = argparse.ArgumentParser(description="Renew Twitch OAuth credentials for bot + channel.")
    parser.add_argument("--env-path", default=str(ROOT / ".env"), help="Path to the .env file to write.")
    parser.add_argument("--bot-only", action="store_true", help="Only refresh bot credentials.")
    parser.add_argument("--channel-only", action="store_true", help="Only refresh channel credentials.")
    parser.add_argument("--bot-client-id", default=None, help="Override BOT_CLIENT_ID (else read from .env).")
    args = parser.parse_args(argv)

    settings = TwitchSettings.load(args.env_path)

    bot_client_id = args.bot_client_id or settings.bot_client_id
    channel_client_id = settings.channel_client_id or bot_client_id

    if not bot_client_id:
        print("BOT_CLIENT_ID missing. Set it in .env or pass --bot-client-id.")
        return 2

    flow = OAuthFlowStarter()
    exit_code = 0

    oauth_port, redirect_uri = _resolve_oauth_port()

    if not args.channel_only:
        exit_code = run_for_account(
            flow, settings, bot_client_id, BOT_SCOPES, "Bot", "BOT", redirect_uri, oauth_port
        ) or exit_code
    if not args.bot_only:
        exit_code = run_for_account(
            flow, settings, channel_client_id, CHANNEL_SCOPES, "Channel/Broadcaster", "CHANNEL", redirect_uri, oauth_port
        ) or exit_code

    settings.reload()
    bot_missing = settings.bot_scopes_missing()
    if bot_missing and not args.channel_only:
        print(f"\nWarning: bot scopes still missing: {', '.join(bot_missing)}")
    channel_missing = settings.channel_scopes_missing()
    if channel_missing and not args.bot_only:
        print(f"\nWarning: channel scopes still missing: {', '.join(channel_missing)}")
    print("\nDone. Review any missing-scope warnings above.")
    print(f"\nRedirect-URI für die Twitch Developer Console:\n  {redirect_uri}")
    print("Trage diese exakt unter Applications → OAuth Redirect URLs ein.")
    if oauth_port != DEFAULT_OAUTH_PORT:
        print(
            f"Hinweis: Der OAuth-Port weicht vom Standard {DEFAULT_OAUTH_PORT} ab. "
            "Stelle sicher, dass die in der Console hinterlegte Redirect-URI "
            f"http://localhost:{oauth_port}/oauth/callback lautet."
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
