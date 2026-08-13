# Runtime (`src/twitchbot_runtime/`)

Modular Twitch bot runtime that processes Twitch events through a
**triggers → reactions** pipeline.

## Layout

| module | role |
|---|---|
| `bot.py` | `TwitchBot`: composes features, resolves triggers, executes reactions; mode-aware handler selection. Constructs `TriggerResolver` + `ReactionEngine` with the `CounterHandler` and `ChatterTracker` injected. |
| `trigger_resolver.py` | `TriggerResolver`: evaluates the `when` tree via `evaluate_when` (payload-bound placeholder resolver + injected counter/chatter tracker); enforces `roles`; emits the un-evaluated `reactions` AST root. |
| `reaction_engine.py` | `ReactionEngine`: dispatches mixed items (AST root with `kind` → `evaluate_reaction_ast`; plain `type` dict → flat dispatch). Engine-side placeholder resolution (counter + args + target + context). |
| `expression/` | nested trigger/reaction tree framework: `nodes.py`, `builder.py` (DSL `C`/`R`), `evaluator.py`, `compare.py`, `condition_match.py`. Zero runtime deps. |
| `eventsub/` | EventSub webhook + subscription client, token validation/refresh, OAuth flow, event normalization, signature verification. |
| `overlay/` | `OverlayManager` + `OverlayFacade` (drives the Overlay_project Flask-SocketIO subprocess). |
| `mode.py` | `Mode` enum (`test`/`silent`/`production`) + legacy alias map. |
| `scheduler.py` | `TimerScheduler`: drives `time` triggers via periodic `handle_event("timer.tick")` calls. |
| `counter_handler.py` | `CounterHandler`: increment/decrement/set/reset/create/delete + subcounters, persists to `counters.json`. |
| `moderation_handler.py` | `ModerationHandler`: ban/timeout/delete/purge (stubs in silent/test). |
| `silent_collector.py` | `SilentEventCollector`: captures events per type to JSONL, capped at N. |
| `test_repl.py` | `ReplSession` + `replay_file`: interactive REPL and JSONL replay for test mode. |
| `ports.py` | configurable/persisted port resolution (`get_port`, `resolve_port_or_exit`, `get_effective_ports`). |
| `chatter_tracker.py` | `ChatterTracker`: in-memory per-channel last-seen map for `new_chatter` (inactivity-window) triggers. |
| `twitch_api.py` | `TwitchApiClient` (Helix base, mode-gated) + `ChatSender`, `ModerationActor`, `ClipCreator`. |
| `twitch_settings.py` | `TwitchSettings`: `.env` wrapper. |
| `tunnel.py` | `TunnelManager`: cloudflared Quick Tunnel start/stop. |
| `schemas.py` | recursive Pydantic models for the trigger/reaction trees. |

## Usage

```bash
python -m twitchbot_runtime --mode test                       # REPL
python -m twitchbot_runtime --mode test --test-file events.jsonl  # replay
python -m twitchbot_runtime --mode silent
python -m twitchbot_runtime --mode production
python -m twitchbot_runtime --show-settings                  # inspect effective settings (no prompts)
```

## Event flow

`TwitchBot.handle_event(event_name, payload)`:

1. Silent mode captures the event via `SilentEventCollector`.
2. For `chat.message` events the `ChatterTracker` records the (channel, username, now) pair **before** trigger resolution, so `new_chatter` window leaves see the latest activity.
3. `TriggerResolver.resolve()` filters by event/role, evaluates each trigger's `when` tree via `evaluate_when`; matching triggers contribute their `reactions` AST root.
4. `FeatureManager.dispatch()` merges feature reactions (plain dicts).
5. `ReactionEngine.execute()` dispatches each item: AST root with `kind` (`seq`/`if`/`switch`/`reaction`) → `evaluate_reaction_ast`; plain `type` dict → flat dispatch by `type`.

## Placeholders

`{username}`, `{args[N]}` (command args), `{target}` (alias for `{args[0]}`),
`{counter:name:field}` (counter handler), and generic `{context_key}`
(e.g. `{channel}`, `{event_name}`). Resolver-side resolution (top-level `when`)
and engine-side resolution (`if.when`/`switch.on` + reaction messages) share
the same order: counter → args → target → context.

## Modes

| mode | description |
|---|---|
| `test` | REPL/replay, no real Twitch calls. Overlay backend starts when `features.overlay.enabled`. No tunnel/EventSub/Twitch API. |
| `silent` | `SilentEventCollector` captures events to JSONL (capped). No outgoing calls, no tunnel, no overlay backend. |
| `production` | Full: EventSub input (cloudflared Quick Tunnel) + overlay backend (when overlay enabled). Sending (chat/ban/delete/clip) via Helix REST (`ChatSender`/`ModerationActor`/`ClipCreator`). |

The overlay backend is gated by `features.overlay.enabled` AND `mode in
(PRODUCTION, TEST)`; `silent` never starts it.

## Trigger types

`command`, `time`, `channel_point_reward`, `first_time_chatter` (Twitch
`chatter_is_new` flag), `new_chatter` (inactivity window via `ChatterTracker`),
`follow`, `sub`, `cheer` (`min_bits`), `raid` (`min_viewers`), `compare`
(field/op/value, placeholder-resolved).

`command` matches a case-insensitive prefix; the message remainder is split
into `args`. `new_chatter` needs an injected `ChatterTracker`; without one the
leaf returns `False` (no false positives). The tracker is in-memory only — a
bot restart loses history, so the first message after a restart counts as "new".

## Build / test

```bash
pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
mypy src
```

The runtime is a pure Python package (`pyproject.toml`, package root `src/`);
no separate deploy step is needed. See [../README.md](../README.md) for ports,
OAuth setup, and the standalone build.
