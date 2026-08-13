# AGENTS.md

Developer reference for the TwitchBot project.

## Project overview

TwitchBot is a modular runtime that processes Twitch events through a triggers → reactions pipeline. Three subprojects:

- `src/twitchbot_runtime/` — Runtime core: event handling, trigger resolution, reaction execution, modes, handlers, overlay bridge.
- `src/Overlay_project/` — Flask-SocketIO overlay (browser-rendered) + StreamPet GIF logic (gifuct-js).
- `src/UI/` — Flask web UI for config management. Reads/writes `settings.json` (Runtime format).

## Architecture

### Event flow

`TwitchBot.handle_event(event_name, payload)` → `TriggerResolver.resolve()` evaluates each trigger's `when` tree (recursive AND/OR/NOT/leaf) via `expression.evaluator.evaluate_when` → matching triggers contribute their **reaction AST root** (un-evaluated) → feature reactions (plain dicts from `FeatureManager.dispatch`) are merged in → `ReactionEngine.execute()` dispatches each item: items with a `kind` field (`seq`/`if`/`switch`/`reaction`) are evaluated as an AST via `expression.evaluator.evaluate_reaction_ast`; plain dicts are dispatched flat by `type` as before.

Trigger leaves (`expression/condition_match.match_event_condition`): `command` / `time` / `channel_point_reward` / `new_chatter` / `follow` / `sub` / `cheer` / `raid` (event-bound) plus the generic `compare` leaf (field/op/value, placeholder-resolved incl. `{counter:...}`).

Reaction handlers (leaf dispatch):
- `send_chat` — `chat_reply`, `clip` follow-up message. Signature `send_chat(broadcaster_id, message)` (numeric `broadcaster_id`; falls back to `context["channel"]` when absent).
- `overlay_dispatch` — `overlay_text`, `overlay_gif`, `streampet`.
- `create_clip` — `clip` (argless; `ClipCreator` reads `TWITCH_CHANNEL_ID` internally).
- `counter_handler` — `counter`.
- `moderation_handler` — `moderation` (target field is placeholder-resolved before dispatch; `ModerationActor` resolves login→id when injected).
- `streampet_handler` — `streampet` (also dispatches to overlay).

Feature reactions (from `FeatureManager.dispatch`) are merged into the reaction list before execution as plain dicts (no `kind`) — the engine dispatches them flat.

**Placeholders** (`ReactionEngine._resolve_placeholders`; also bound resolver-side in `TriggerResolver._build_payload_resolver`): `{username}`, `{counter:name:field}` (via counter handler), `{args[N]}` (command args, extracted by `match_event_condition` for `type==command`), `{target}` (alias for `{args[0]}`), and generic `{context_key}` (e.g. `{event_name}`, `{channel}` from the payload/context). Missing args/index → token left intact. `compare` leaves and `if.when`/`switch.on` use the same resolver.

### Modes (`src/twitchbot_runtime/mode.py`)

- `test` — REPL/replay, no real Twitch calls. Side-effects replaced with in-memory collectors. When `features.overlay.enabled` is set, the overlay backend (Flask-SocketIO subprocess) **is** started so overlay features can be exercised end-to-end; the overlay port is resolved (and persisted on first run) the same way as in production. No tunnel, no EventSub, no Twitch API calls.
- `silent` — `SilentEventCollector` captures events to JSONL (per type, capped at `runtime.silent_max_per_type`, default 50). No outgoing calls, no tunnel, no overlay backend.
- `production` — full operation: EventSub input (via cloudflared Quick Tunnel) + overlay backend (when `features.overlay.enabled`). Sending (chat/ban/delete/clip) goes through Helix REST via `TwitchApiClient` + `ChatSender`/`ModerationActor`/`ClipCreator` using the Bot user token. `TwitchApiClient` with `mode != PRODUCTION` guarantees NO network calls (early-return stubs).

The overlay backend is gated by `features.overlay.enabled` AND `mode in (PRODUCTION, TEST)` — `silent` never starts it (pure event capture). In `bot.py`: `real_backend = overlay_enabled and self.mode in (Mode.PRODUCTION, Mode.TEST)`. The `overlay` port is resolved (and the first-run prompt offered) only when `real_backend` is true.

`Mode.from_string` accepts legacy aliases `bot` → `production`, `log_only` → `silent`.

### Credentials & startup sequence

Account secrets live in `.env` (project root, gitignored), wrapped by `TwitchSettings` (`src/twitchbot_runtime/twitch_settings.py`). `settings.json` keeps only `twitch.webhook_secret`; `callback_url` is built at runtime from the cloudflared tunnel. Renew tokens with `python scripts/get_all_scopes.py` (runs the OAuth browser flow for Bot + Channel with the full scope set).

**OAuth redirect URI:** `get_all_scopes.py` uses `OAuthFlowStarter` with `DEFAULT_REDIRECT_URI = http://localhost:5003/oauth/callback` (`oauth_flow.py`). This must exactly match a redirect URI registered in the Twitch Dev Console app settings (Applications → app → OAuth Redirect URLs), or Twitch rejects the authorization. The EventSub webhook `callback_url` (cloudflared, port 5002) is separate and is not a redirect URI. Setup workflow in `README.md` "Twitch app registration & OAuth setup".

Startup (production, in `TwitchBot._run_startup_checks`): `TwitchSettings.load()` → `TokenValidator.validate` bot token (refresh via `TokenRefresher` if invalid; OAuth flow if refresh fails) → validate channel token → fallback `ChannelIdFetcher` for `TWITCH_CHANNEL_ID` → `AppTokenFetcher.fetch` (client_credentials, cached) → `TunnelManager.start` (cloudflared Quick Tunnel → `https://<random>.trycloudflare.com`, `callback_url = public_url + "/eventsub"`) → webhook server → `EventSubClient.register_subscriptions`. silent/test skip all network steps.

Scope mapping (source of truth): see `docs/settings.example.json` triggers and `TRIGGER_HINTS` in `src/UI/Backend/UI.py`. Bot token needs all send + receive scopes; channel token is read-only. Bot must be a moderator of the channel (`moderator_user_id`/`moderator_id` = `BOT_CHANNEL_ID`).

### Config

Single source of truth: `settings.json`. Top-level keys:

- `runtime.execution_mode` — one of `test` / `silent` / `production`.
- `features` — feature enable flags (`moderation`, `overlay`, `streampet`, `webui`).
- `triggers` — list of trigger entries in Runtime format. Each trigger has `name`, optional `event` (pre-filter), a `when` tree (recursive `kind`-discriminator: `and`/`or`/`not`/`leaf`), `roles`, and a `reactions` AST root (`seq`/`if`/`switch`/`reaction`).
- `overlay` — overlay display config.

No more `commands.json`. `settings.json["commands"]` (legacy flat format) is read only as a fallback by the UI backend; new configs use `triggers` with the `when`/`reactions` root format. Legacy `triggers.conditions` (flat `all`/`any` + `conditions` list) and `conditions:{all,any}` are **no longer read** by the resolver.

### Reaction types

`ReactionType` = `chat_reply` / `overlay_text` / `overlay_gif` / `clip` / `counter` / `moderation` / `streampet` (Runtime format). Used consistently across `ReactionEngine`, `schemas.py`, and the UI.

### Serialized trigger/reaction format

Both the Runtime and the Web-UI read/write the same `kind`-discriminator dict form. Build trees in code with the `C`/`R` DSL (`expression/builder.py`); serialize via `.to_dict()`.

**Trigger side** — `trigger["when"]` is a single root node:

```jsonc
// Event leaf (existing TriggerCondition wrapped)
{ "kind": "leaf", "condition": { "type": "command", "command": "!hello" } }
// Compare leaf: field is placeholder-resolved (incl. {counter:...})
{ "kind": "leaf", "condition": { "type": "compare", "field": "{counter:deaths:value}", "op": ">=", "value": 5 } }
// Logic nodes
{ "kind": "and", "children": [ <node>, ... ] }   // alias "all" accepted
{ "kind": "or",  "children": [ <node>, ... ] }   // alias "any" accepted
{ "kind": "not", "child": <node> }
```

Empty `and` → True; empty `or` → False; `not` without child → schema error.

**Reaction side** — `trigger["reactions"]` is a single root node:

```jsonc
{ "kind": "reaction", "reaction": { "type": "chat_reply", "message": "hi {username}" } }
{ "kind": "seq", "children": [ <ast>, ... ] }
{ "kind": "if", "when": <trigger-node>, "then": <ast>, "else": <ast> }
{ "kind": "switch", "on": "{args[0]}", "cases": [ { "equals": "red", "then": <ast> } ], "default": <ast> }
```

`if.when` uses the same trigger-node format (incl. `compare`); `if`/`switch` use **engine-side** placeholder resolution (counter available). The top-level `when` uses **resolver-side** resolution (counter injected via `TriggerResolver(counter_handler=...)`).

## Overlay subsystem

`OverlayFacade` (`src/twitchbot_runtime/overlay/facade.py`) drives `Overlay_project` (Flask-SocketIO + StreamPet GIF engine) in a `multiprocessing` subprocess.

### Action payload contract (Runtime → Overlay)

Messages put on `facade.queue` are shaped `{"action": <type>, "data": {...}}`:

- `{"action": "StreamPet", "data": {"animation": <name>, "username": <str>, ...}}` — trigger a StreamPet animation.
- `{"action": "overlay_text", "data": {"text": <str>}}` — show a text overlay (5s server-side TTL via `RenderingService._prune_messages`).
- `{"action": "overlay_gif", "data": {"gif_id": <str>, "text": <str>}}` — show a gif overlay.

The legacy `change_color` action has been removed (no `OverlayAction` literal anymore; `action` in `CommandReaction` is plain `str | None`).

### Control channel vs. data channel

Two queue concepts are deliberately separated:

- **`facade.queue`** (`multiprocessing.Queue`) — parent→child IPC. Carries overlay action payloads (data) **and** the `"STOP"` control token. Primary stop path: `running_event.clear()` (a `multiprocessing.Event`, visible across the process boundary) + `queue.put_nowait("STOP")` (triggers `socketio.stop()` so the blocking `websocket_handler.start()` returns).
- **`StreamPet.queue`** (`queue.Queue`, threading) — internal to the animation engine; `"STOP"` never reaches it.

### Stop strategy (cross-platform)

Primary stop is queue/event-driven (works on both Windows `spawn` and Linux `fork`):

1. `running_event.clear()` — before `join()`, visible in the child; the inner drain loop and `update_loop` break on the next flag check.
2. `queue.put_nowait("STOP")` — triggers `socketio.stop()` so the blocking `websocket_handler.start()` returns.
3. `process.join(timeout=5)` — wait for clean exit.
4. `process.terminate()` — last-resort hard stop after timeout. **Platform delta:** POSIX = `SIGTERM` (the child's signal handler from `_run_overlay` runs, can clean up); Windows = `TerminateProcess` (hard kill, no handler). Because the primary path is queue/event-driven, `terminate()` is only defense-in-depth.

No `os.kill`/external `SIGTERM` is sent from the parent (unreliable on Windows). The child's `SIGTERM` handler (`overlay_helpers.handle_signals`) only fires on real terminal signals, not on `process.terminate()` under Windows.

### Frame control (client drives)

The browser (`overlay.js`) advances frames locally via `requestAnimationFrame`; the server sends a `frame` field in the `update` payload for backward compatibility but the client ignores it for rendering — only `animation` is authoritative for animation switches (resets the local counter to 0).

## Configurable & persisted ports

The five historically hardcoded service ports are configurable and persisted in `settings.json` under `runtime.<component>.port`. Central logic lives in `src/twitchbot_runtime/ports.py`:

- `DEFAULT_PORTS = {"overlay": 5000, "webui": 5001, "webhook": 5002, "pos_ui": 5003, "oauth": 5003}`.
- `get_port(component, settings, settings_path, *, interactive, host, persist)` — resolves a port: persisted value (no prompt) → default → interactive prompt on first run (TTY only, persisted) → non-interactive default (NOT persisted, warning logged) → freedom check via `is_port_free`.
- `resolve_port_or_exit(...)` — wrapper that exits with code 1 + free-alternative suggestions on `PortInUseError`.
- `get_effective_ports(settings)` — status snapshot for the Config-UI `GET /api/ports` (never prompts/persists).
- `settings.py` default dict deliberately does NOT include the new port keys — a missing key is the signal that triggers the first-run prompt. Pre-populating defaults would suppress it forever.

### Resolution points

- **Bot** (`bot.py`): resolves `overlay` (only when `mode in (PRODUCTION, TEST) AND features.overlay.enabled`) and `webhook` (cached on `self._webhook_port` via `_resolve_webhook_port` so the server and the cloudflared tunnel share one resolution + freedom check). Silent never resolves overlay; test resolves overlay only when overlay is enabled; silent resolves webhook (no overlay).
- **Config-UI** (`UI.py`): `resolve_port_or_exit("webui", ...)` in `__main__`; `GET/POST /api/ports` endpoints for the Ports section.
- **Pos-UI** (`overlay_pos_ui/app.py`): `OVERLAY_POS_UI_PORT` env var (highest priority, not persisted, backward-compat) → `resolve_port_or_exit("pos_ui", ...)`. The "view in overlay" HTML link reads `runtime.overlay.port` (default 5000) via `_read_overlay_port_from_settings` (never prompts).
- **OAuth** (`scripts/get_all_scopes.py`): `_resolve_oauth_port()` builds `redirect_uri` from the resolved port and warns when it differs from 5003 (Twitch Console Redirect URI must match). `OAuthFlowStarter.start_and_wait` already accepts explicit `port` + `redirect_uri`.
- **Overlay subprocess** (`overlay/facade.py`): `OverlayFacade(overlay_port=...)` → `Process(args=(queue, running_event, overlay_port))` → `_run_overlay` binds `websocket_handler.start(port=overlay_port)` and passes `overlay_url` to `open_browser_when_ready`.
- **`OverlayManager._create_real_backend(overlay_port)`** is a staticmethod (cannot read instance attrs) — the port is passed as a param from `__init__`.
- **`--show-settings`** (`__main__.py`) never calls `get_port` (no prompt).

### Port-in-use behavior

Occupied port → `PortInUseError(host, port, alternatives=find_free_alternatives(...))` → `resolve_port_or_exit` prints a stderr message with free alternatives and exits 1. No auto-fallback (per decision: the user must explicitly choose). Race between probe and bind is best-effort; a bind failure after a successful probe is also treated as port-in-use.

## Build / Test commands

Run from project root unless noted.

| Task | Command |
| --- | --- |
| Python tests | `python -m pytest -q` |
| UI Jest tests | `cd src/UI/static && npm test` (run `npm install` first in that dir) |
| Overlay JS bundle | `cd src/Overlay_project && npm run build` (run `npm install` first; `npm run dev` for watch mode) |
| Show effective settings | PowerShell: `$env:PYTHONPATH="src"; python -m twitchbot_runtime --show-settings`<br>bash: `PYTHONPATH=src python -m twitchbot_runtime --show-settings` |
| Test mode REPL | `python -m twitchbot_runtime --mode test` |
| Replay JSONL events | `python -m twitchbot_runtime --mode test --test-file events.jsonl` |
| Silent mode | `python -m twitchbot_runtime --mode silent` |
| All tests at once | `scripts/run_all_tests.bat` (Windows) / `scripts/run_all_tests.sh` (Linux); Node steps skip if `npm` missing |
| Launcher menu | `start.bat` (Windows) / `start.sh` (Linux); requires `.venv` in project root |
| Overlay-Positions-UI | `PYTHONPATH=src python -m twitchbot_runtime.overlay_pos_ui` (port 5003, `OVERLAY_POS_UI_PORT` overrides) |

Python tests insert `src/` into `sys.path` via the header below; no `PYTHONPATH` needed for pytest.

Lint/typecheck (configured in `pyproject.toml`): `ruff check .` and `mypy src`.

## Packaging

`pyproject.toml` declares the build backend (`setuptools`), package root `src/`, and optional dependency groups: `[overlay]` (flask/flask-socketio/pillow), `[dev]` (pytest/pytest-mock), `[all]`. Runtime deps are in `requirements.txt`; dev/test deps in `requirements-dev.txt`. Build a wheel with `python -m build`.

A standalone venv-tarball is produced by `.github/workflows/release.yml` (matrix: `windows-latest` + `ubuntu-latest`, on `workflow_dispatch` or `v*` tags). It bundles the project plus a pre-built `.venv` and `overlay.bundle.js`, excluding `.git`/`node_modules`/caches. The venv records absolute paths — moving the extracted folder may break activation (documented in README).

CI (`.github/workflows/ci.yml`) runs on every push/PR: a non-blocking `lint` job (`ruff` + `mypy` with GitHub-format inline annotations, `continue-on-error`) and a blocking `test` job (pytest + UI Jest + Overlay build).


## Conventions

- **Test file header** (required first lines of every `tests/*.py`):
  ```python
  import sys
  from pathlib import Path

  ROOT = Path(__file__).resolve().parents[1]
  sys.path.insert(0, str(ROOT / "src"))
  ```
- **OverlayManager tests** must NEVER start the real `OverlayFacade` (spawns Flask on port 5000). Use a `DummyBackend` + `staticmethod(factory)` monkeypatch pattern, or inject `backend=` directly:
  ```python
  monkeypatch.setattr(OverlayManager, "_create_backend", staticmethod(factory))
  ```
- **Counter persistence**: `counters.json`, keyed as `"name:category"`.
- **Settings**: `settings.json` is the single source of truth (no more `commands.json`).
- **No comments** in code unless absolutely necessary.

## Key files

- `src/twitchbot_runtime/bot.py` — `TwitchBot`: composes features, resolves triggers, executes reactions; mode-aware handler selection. Constructs `TriggerResolver` with the `CounterHandler` injected (so `compare` leaves resolve `{counter:...}` resolver-side).
- `src/twitchbot_runtime/expression/` — nested trigger/reaction tree framework: `nodes.py` (dataclasses `And`/`Or`/`Not`/`Leaf` + `Seq`/`If`/`Switch`/`ReactionNode` with `to_dict`/`from_dict`), `builder.py` (code-DSL `C`/`R`), `evaluator.py` (`evaluate_when`, `evaluate_reaction_ast`, `walk_trigger_leaves`, `walk_reaction_leaves`), `compare.py` (`compare` leaf ops), `condition_match.py` (shared event-leaf matcher + `payload_roles`/`matches_roles`). Zero runtime deps; tested in isolation.
- `src/twitchbot_runtime/trigger_resolver.py` — `TriggerResolver`: evaluates the `when` tree via `evaluate_when` (with a payload-bound placeholder resolver + injected `counter_handler`); enforces `roles` (mod/broadcaster) from `payload.roles`/`payload.badges`; emits the un-evaluated `reactions` AST root. Legacy `triggers.conditions`/`conditions:{all,any}` paths removed.
- `src/twitchbot_runtime/reaction_engine.py` — `ReactionEngine`: `execute()` dispatches mixed items (AST root with `kind` → `evaluate_reaction_ast`; plain `type` dict → flat dispatch). `evaluate_reaction_ast` (in `expression/evaluator.py`) evaluates `seq`/`if`/`switch`/`reaction` with engine-side placeholder resolution (counter + args + target + context). Resolves `{username}` and `{counter:name:field}` placeholders in `chat_reply` messages.
- `src/twitchbot_runtime/mode.py` — `Mode` enum (`test`/`silent`/`production`) + `from_string` legacy alias map.
- `src/twitchbot_runtime/ports.py` — configurable/persisted port resolution: `DEFAULT_PORTS`, `get_port`, `resolve_port_or_exit`, `get_effective_ports`, `PortInUseError`, `is_port_free`, `find_free_alternatives`. Interactive prompt on first run (TTY), default without persistence when non-interactive, freedom check via socket bind.
- `src/twitchbot_runtime/counter_handler.py` — `CounterHandler`: increment/decrement/set/reset/create/delete + subcounters, persists to `counters.json`.
- `src/twitchbot_runtime/moderation_handler.py` — `ModerationHandler`: ban/timeout/delete/purge (stubs in silent/test).
- `src/twitchbot_runtime/silent_collector.py` — `SilentEventCollector`: captures events per type to JSONL, capped at N.
- `src/twitchbot_runtime/test_repl.py` — `ReplSession` + `replay_file`: interactive REPL and JSONL replay for test mode.
- `src/twitchbot_runtime/scheduler.py` — `TimerScheduler`: drives `time` triggers via periodic `handle_event("timer.tick")` calls (silent/production). Computes the coarsest interval via `walk_trigger_leaves` over `trigger["when"]`.
- `src/twitchbot_runtime/eventsub/server.py` — Flask EventSub webhook receiver (port 5002, separate from overlay/UI); signature verification + challenge response + event dispatch.
- `src/twitchbot_runtime/eventsub/client.py` — `EventSubClient`: registers/deletes Twitch EventSub subscriptions via Helix API. Accepts `TwitchSettings` or a dict; `_condition_for` uses `bot_user_id` for chat/follow; supports injected `AppTokenFetcher`. `subscription_types_for_triggers` walks `trigger["when"]` via `walk_trigger_leaves` (compare leaves contribute no EventSub type).
- `src/twitchbot_runtime/eventsub/token_validator.py` — `TokenValidator`: `GET /oauth2/validate`.
- `src/twitchbot_runtime/eventsub/token_refresher.py` — `TokenRefresher`: refresh user token + persist to `.env`.
- `src/twitchbot_runtime/eventsub/channel_id.py` — `ChannelIdFetcher`: resolve login → numeric id.
- `src/twitchbot_runtime/eventsub/app_token.py` — `AppTokenFetcher`: client_credentials app token (cached).
- `src/twitchbot_runtime/eventsub/oauth_flow.py` — `OAuthFlowStarter`: authorize URL + code exchange; `BOT_SCOPES`/`CHANNEL_SCOPES`.
- `src/twitchbot_runtime/eventsub/verify.py` — HMAC-SHA256 signature verification + challenge detection.
- `src/twitchbot_runtime/eventsub/events.py` — maps EventSub `subscription.type` → runtime `(event_name, payload)`; extracts `is_new_chatter` (`chatter_is_new`), `broadcaster_id` (`broadcaster_user_id`), and maps badges → `roles`.
- `src/twitchbot_runtime/twitch_settings.py` — `TwitchSettings`: `.env` wrapper (load/write_env, missing-scopes, Bot/Channel split).
- `src/twitchbot_runtime/tunnel.py` — `TunnelManager`: cloudflared Quick Tunnel start/stop + trycloudflare URL parsing.
- `src/twitchbot_runtime/twitch_api.py` — `TwitchApiClient` (Helix base, mode-gated) + `ChatSender`, `ModerationActor` (login→id cache), `ClipCreator`.
- `src/twitchbot_runtime/schemas.py` — recursive Pydantic models: `TriggerNode` (discriminated union `AndNode`/`OrNode`/`NotNode`/`LeafNode`), `ReactionNode` (`SeqNode`/`IfNode`/`SwitchNode`/`ReactionLeafNode`), `CommandSchema` (`when: TriggerNode`, `reactions: ReactionNode`), `CommandsDocument`, `ReactionType`, `TriggerCondition` (incl. `compare` field/op/value). All models keep `extra: allow`. `empty_command()` builds the default `when`/`reactions` root template.
- `src/twitchbot_runtime/config_schema.py` — `build_config_schema_message()`: produces the JSON schema served by the UI; `_resolve_refs` is cycle-aware (recursive `$ref`s are left in place + `$defs` kept).
- `src/twitchbot_runtime/overlay/manager.py` — `OverlayManager`: facade coordinating overlay actions + lazy backend.
- `src/twitchbot_runtime/overlay/facade.py` — `OverlayFacade`: starts the Overlay_project process (Flask-SocketIO + StreamPet).
- `src/twitchbot_runtime/overlay_pos_ui/` — Overlay-Positions-UI: Flask app (port 5003, `OVERLAY_POS_UI_PORT`) editing `Stream_Pet.json` via Drag&Drop canvas; position in `0..1` space (matches `ConfigPositionTracker`); path-traversal-safe `/StreamPet/<filename>` (mirrors `overlay_server.py`).
- `src/UI/Backend/UI.py` — Flask app exposing `/api/config_schema`, `/api/commands`, `/api/settings`, `/api/trigger_hints` (per-type scope/freigabe hints).
- `src/UI/static/commands.js` — recursive UI editor: `renderWhen` (AND/OR/NOT/leaf + compare editor) and `renderReactions` (seq/if/switch/reaction); `createMockCommand` emits the `when`/`reactions` root format; 9 trigger leaf types incl. `compare`; schema-driven enums with hardcoded fallbacks.
- `scripts/get_all_scopes.py` — CLI to renew Bot + Channel OAuth tokens with the full scope set.
- `scripts/run_all_tests.bat` / `scripts/run_all_tests.sh` — run pytest (blocking) + UI Jest + Overlay build; Node steps skip with warning if `npm` missing.
- `start.bat` / `start.sh` — repo-root launcher menu (Config-UI / Pos-UI / Bot / Tests); requires `.venv`, prints setup hint if missing.
- `.github/workflows/ci.yml` — CI: non-blocking `lint` (ruff/mypy inline annotations) + blocking `test` (pytest + UI Jest + Overlay build).
- `.github/workflows/release.yml` — standalone venv-tarball builder (Windows + Linux matrix, on `workflow_dispatch`/`v*` tags).
