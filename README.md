# TwitchBot

A Python-based Twitch bot runtime that loads JSON-configured triggers and reactions, processes Twitch EventSub webhooks, renders a browser overlay (StreamPet GIFs + text/GIF overlays), and ships a Flask web UI for configuration.

## Current architecture

- `src/twitchbot_runtime/` — modular runtime: event handling, trigger resolution, reaction execution, modes, handlers, overlay bridge, EventSub webhook + subscription client, timer scheduler.
- `src/Overlay_project/` — Flask-SocketIO overlay (browser-rendered) + StreamPet GIF logic (gifuct-js).
- `src/UI/` — Flask web UI for config management. Reads/writes `settings.json` (Runtime format).

### Event flow

`TwitchBot.handle_event(event_name, payload)` → `TriggerResolver.resolve()` matches triggers by conditions (`command` / `time` / `channel_point_reward` / `first_time_chatter` / `new_chatter` / `follow` / `sub` / `cheer` / `raid` / `compare`) → matched reactions collected → `ReactionEngine.execute()` dispatches each reaction to a handler. In silent/production, events arrive via the EventSub webhook on port 5002; in test mode, via the REPL/replay. See [docs/runtime.md](docs/runtime.md) for the full event flow and placeholder system.

## Requirements

- Python 3.10+ (uses `from __future__ import annotations`)
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```
- A `settings.json` for runtime configuration (see `docs/settings.example.json`)
- Twitch app credentials (client id/secret + a public callback URL) for silent/production

## Running the bot

The runtime has three execution modes:

| mode | description |
|---|---|
| `test` | Interactive REPL / JSONL replay; no Twitch connection, no outgoing calls (default when no `settings.json` exists). |
| `silent` | Subscribes to real EventSub events (same input as production) but sends no chat/moderation/clip calls; captures events to `output/silent_events.jsonl`. |
| `production` | Full operation: EventSub webhook input (via cloudflared Quick Tunnel), browser overlay. Outbound chat/clip/moderation go through Helix REST via `TwitchApiClient` + `ChatSender`/`ModerationActor`/`ClipCreator` using the Bot user token. |

> The legacy `bot` / `log_only` mode names are still accepted as aliases for `production` / `silent`.

### Start in test mode (REPL)
```bash
python -m twitchbot_runtime --mode test
```

### Replay recorded events
```bash
python -m twitchbot_runtime --mode test --test-file events.jsonl
```

### Start in silent mode
```bash
python -m twitchbot_runtime --mode silent
```

### Start in production mode
```bash
python -m twitchbot_runtime --mode production
```

### Inspect settings without starting
```bash
python -m twitchbot_runtime --show-settings
python -m twitchbot_runtime --mode silent --show-settings
```

## EventSub setup (silent/production)

Both silent and production receive real Twitch events through an EventSub webhook receiver. You need a publicly reachable callback URL (the runtime starts a cloudflared Quick Tunnel automatically in production, producing `https://<random>.trycloudflare.com`) and app credentials in `settings.json`:

```json
{
  "twitch": {
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "webhook_secret": "a-shared-secret",
    "callback_url": "https://<your-public-host>/eventsub",
    "broadcaster_user_id": "123456789"
  },
  "runtime": {
    "execution_mode": "silent",
    "webhook": {"host": "127.0.0.1", "port": 5002}
  }
}
```

The webhook server listens on port `5002` by default (configurable via `runtime.webhook.port`; see [Ports](#ports)). The runtime registers EventSub subscriptions after the webhook is listening, so Twitch can verify the callback immediately. In production, `callback_url` is built at runtime from the cloudflared tunnel public URL (the `callback_url` in `settings.json` is a fallback). Outbound chat/clip/moderation in production go through Helix REST (`ChatSender`/`ClipCreator`/`ModerationActor`); `handle_event` is the input contract.

## Twitch app registration & OAuth setup

The bot needs two user tokens (Bot account + Channel/Broadcaster account). Generate or renew them with:

```bash
python scripts/get_all_scopes.py            # both accounts
python scripts/get_all_scopes.py --bot-only  # just the bot account
python scripts/get_all_scopes.py --channel-only
```

The script runs the Twitch OAuth **Authorization-Code flow**: it prints an authorize URL, you open it in a browser and consent, Twitch redirects to a tiny local Flask callback on `http://localhost:5003/oauth/callback`, and the captured code is exchanged for an `(access_token, refresh_token)` pair that is written into `.env`. At the end the script prints the exact redirect URI to register in the Twitch Developer Console.

> **Redirect URI requirement:** The redirect URI used by the flow **must exactly match** a redirect URI registered for your Twitch app in the Dev Console. The default is `http://localhost:5003/oauth/callback`. If the strings do not match byte-for-byte (scheme, host, port, path), Twitch rejects the authorization with `400 redirect_uri_mismatch`. The Config-UI Ports section also shows the exact, copyable redirect URI (built from the resolved OAuth port).

### Registering the redirect URI in the Twitch Dev Console

1. Open the [Twitch Developer Console](https://dev.twitch.tv/console) and sign in.
2. Go to **Applications** → your app → **Manage** (or create a new app first).
3. In the app settings, locate the **OAuth Redirect URLs** field.
4. Add the exact value: `http://localhost:5003/oauth/callback`
   - One URL per line. No trailing slash. The scheme (`http`) and port (`5003`) must match what the flow uses (see `DEFAULT_REDIRECT_URI` / `DEFAULT_OAUTH_PORT` in `src/twitchbot_runtime/eventsub/oauth_flow.py`).
5. Save the app settings. The change is effective immediately; no app re-creation needed.
6. Run `python scripts/get_all_scopes.py` — the browser redirect should now land on the local callback and the token exchange should succeed.

If you run the flow on a different port (e.g. via `OAuthFlowStarter(... port=...)`), register that URI instead. The EventSub webhook callback (`callback_url`, built from the cloudflared tunnel on port 5002) is **separate** and does not need to be registered as a redirect URI — only the OAuth `localhost:5003` callback does.

## Ports

All five service ports are configurable and persisted in `settings.json` under `runtime.<component>.port`:

| service | config key | default | notes |
|---|---|---|---|
| Overlay (Flask-SocketIO) | `runtime.overlay.port` | 5000 | subprocess via `OverlayFacade` |
| Web UI (Flask) | `runtime.webui.port` | 5001 | `src/UI/Backend/UI.py` |
| EventSub webhook (Flask) | `runtime.webhook.port` | 5002 | host via `runtime.webhook.host` |
| Overlay-Positions-UI (Flask) | `runtime.pos_ui.port` | 5003 | `OVERLAY_POS_UI_PORT` env var still wins (not persisted) |
| OAuth callback (one-shot Flask) | `runtime.oauth.port` | 5003 | `scripts/get_all_scopes.py` only |

### First-run port prompt

When a port entry is **missing** from `settings.json` and the process runs on a TTY, the bot/UI/Pos-UI/OAuth script prompts once (default pre-filled) and persists the chosen value. On subsequent starts the persisted port is used directly. In non-interactive (headless) runs the default is used **without** being persisted, and a warning points at the Config-UI Ports section.

### Port-in-use check

Every resolved port is probed with a real socket bind before the service starts. If the port is already taken, the process exits with code 1 and prints free alternatives, e.g.:

```
Error: port 5003 on 127.0.0.1 is already in use.
Free alternatives you could set in settings.json or the Config-UI: 5004, 5005, 5006
```

### OAuth port warning

Changing the OAuth port (`runtime.oauth.port`) requires updating the **Redirect URI** in the [Twitch Developer Console](https://dev.twitch.tv/console) (Applications → your app → OAuth Redirect URLs) to `http://localhost:<port>/oauth/callback`, otherwise authorization fails with `400 redirect_uri_mismatch`. The code prints an advisory warning but cannot enforce this — it is your responsibility to keep them in sync.

### Config-UI Ports section

The Config-UI (`src/UI/Backend/UI.py`) exposes a Ports section with a live status table (port, default, free/occupied) and per-component save buttons. Endpoints:

- `GET /api/ports` → `{ports: {<component>: {port, default, free}}, oauth_warning?: string, oauth_redirect_uri: string}`
- `POST /api/ports` → body `{component, port}`, validates `1..65535`, persists to `settings.json`, returns the updated snapshot plus a `warning` field for OAuth changes and the `oauth_redirect_uri` field. The Ports section renders the exact, copyable OAuth redirect URI below the table.

> The `--show-settings` flag never prompts for ports — it just prints the effective settings (with defaults filled in for missing entries).

## Configuration

The runtime reads its entire configuration from a single `settings.json` file. There is no separate `commands.json`. See [docs/settings.example.json](docs/settings.example.json) for the full schema and [docs/ui.md](docs/ui.md) for the WebUI.

### Trigger types (Runtime format)

- `command` — matches a chat command (case-insensitive prefix); the remainder becomes `args`
- `time` — fires on a configurable timer interval
- `channel_point_reward` — fires when a channel point reward is redeemed
- `first_time_chatter` — fires when Twitch marks a chatter as first-time (`chatter_is_new` flag)
- `new_chatter` — fires for a chatter whose last message is older than a configurable inactivity window (`time` seconds) or who has never spoken
- `follow` / `sub` / `cheer` (optional `min_bits`) / `raid` (optional `min_viewers`) — EventSub-bound
- `compare` — generic comparison leaf (field/op/value, placeholder-resolved incl. `{counter:...}`)
- `role` — role check (mod/broadcaster/vip/subscriber; Broadcaster always passes). Used in `if.when` for per-case role gating inside the reaction tree (e.g. the counter scaffolder), also valid in `when`.

### Reaction types (Runtime format)

- `chat_reply` - send a chat message
- `overlay_text` - show text on the overlay
- `overlay_gif` - show a GIF on the overlay
- `clip` - request clip creation
- `counter` - trigger counter handler (single-construct switch with `category_dependent` + auto-create; see [docs/ui.md](docs/ui.md) "Counters")
- `moderation` - trigger moderation handler
- `streampet` - trigger a StreamPet animation

### Placeholders

Reaction messages and `compare` fields resolve placeholders: `{username}`, `{args[N]}` (command args), `{target}` (alias for `{args[0]}`), `{counter:name:field}`, and generic `{context_key}` (e.g. `{channel}`, `{event_name}`). The Config-UI shows a live preview of resolved placeholders for `chat_reply`/`overlay_text`/`overlay_gif`.

## Testing

Python tests:
```bash
python -m pytest -q
```

UI Jest tests (run `npm install` first in that dir):
```bash
cd src/UI/static && npm test
```

UI Flask tests are skipped automatically when Flask is not installed; install `requirements.txt` (or at least `flask`) to run them.

### All tests at once

Run Python + UI Jest + Overlay JS build in one go (Node steps skip with a warning when `npm` is missing):
```bash
scripts/run_all_tests.bat   # Windows
scripts/run_all_tests.sh    # Linux
```
Exit code is non-zero only when the Python tests fail; the Node steps are best-effort.

## Local start menu

`start.bat` (Windows) / `start.sh` (Linux) in the repo root open a 4-option menu:

1. Config-UI — `src/UI/Backend/UI.py` (port from `runtime.webui.port`, default 5001)
2. Overlay-Positions-UI — `python -m twitchbot_runtime.overlay_pos_ui` (port from `runtime.pos_ui.port`, default 5003)
3. Bot in production mode — `python -m twitchbot_runtime --mode production`
4. Run all tests — calls `scripts/run_all_tests.*`

Both scripts require a populated `.venv` in the project root and print a setup hint (no auto-setup) if it is missing:
```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # Linux
.venv\Scripts\pip install -r requirements-dev.txt  # Windows
```

## Overlay-Positions-UI

A standalone Flask app (no Socket.IO) for editing `Stream_Pet.json` via a Drag&Drop canvas:

```bash
python -m twitchbot_runtime.overlay_pos_ui
# then open http://localhost:5003
```

- Loads `Stream_Pet.json` and the idle StreamPet GIF into a draggable preview.
- Position is stored as `position.x/y` in the `0..1` coordinate space (matching `ConfigPositionTracker.resolve`, which multiplies by screen dimensions).
- Sliders/inputs cover `height`, `text_size`, `speech_bubble_position`, `speech_bubble_text`, `speech_bubble_toggle`.
- "Speichern" writes the full config back to `Stream_Pet.json`.
- Override the port with `OVERLAY_POS_UI_PORT` (takes priority, not persisted) or `runtime.pos_ui.port` in `settings.json` if 5003 is taken (note the OAuth callback in `scripts/get_all_scopes.py` also uses 5003 by default — run them at different times or override one).

## Standalone build (CI)

The `Release` workflow (`.github/workflows/release.yml`) builds a self-contained tarball on Windows + Linux runners. Trigger it manually via the Actions tab (`workflow_dispatch`) or by pushing a `v*` tag.

Each archive contains the full project plus a pre-built `.venv` and the bundled `overlay.bundle.js`, excluding `.git`, `node_modules`, and caches. Download the artifact for your OS, extract it, and run `start.bat`/`start.sh`.

> **venv portability caveat:** the bundled `.venv` records absolute paths. Keep the extracted folder where it was built, or recreate the venv with `python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt` after moving it. A tarball built on Windows only works on Windows (and vice versa).

## CI

The `CI` workflow (`.github/workflows/ci.yml`) runs on every push and pull request:

- **lint job** (non-blocking, `continue-on-error`): `ruff check --output-format=github .` and `mypy src` post inline annotations. `--output-format=github` was removed from mypy 2.x (it caused a Usage error → Exit 2); default output emits `path:line: error:` lines GitHub parses. Existing lint findings stay visible without failing the build.
- **test job** (blocking): `python -m pytest -q`, then `cd src/UI/static && npm ci && npm test` (Node 22), then `cd src/Overlay_project && npm ci && npm run build`.

## Documentation

- [docs/runtime.md](docs/runtime.md) — runtime architecture, event flow, placeholders, modes, ports
- [docs/overlay.md](docs/overlay.md) — overlay subsystem (Flask-SocketIO + StreamPet GIF engine, subprocess IPC)
- [docs/ui.md](docs/ui.md) — Config-UI + Overlay-Positions-UI (Flask backend + JS editor + labels map)
- [docs/deployment.md](docs/deployment.md) — manual deployment pipeline (`scripts/deploy_manual.*` + `deploy-manual.yml`)
- [docs/settings.example.json](docs/settings.example.json) — annotated example configuration
