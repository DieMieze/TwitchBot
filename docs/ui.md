# Config-UI (`src/UI/`)

Flask web UI for editing `settings.json` (triggers/reactions in the Runtime
AST format) and managing StreamPet, ports, and features. Reads/writes the same
`settings.json` the runtime consumes.

## Layout

- `Backend/UI.py` — Flask app exposing the API endpoints and serving `index.html`.
- `static/commands.js` — recursive trigger/reaction UI editor (`renderWhen`,
  `renderLeafCondition`, `renderReactions`, `renderReactionLeaf`).
- `static/labels.js` — central frontend label/hint map (display names for
  trigger/reaction types and AST node kinds, matching hints, placeholder docs).
- `static/ports.js` / `features.js` / `streampet.js` — the other UI sections.
- `index.html` — section shell + script includes (`labels.js` before
  `commands.js`, since `commands.js` calls `displayLabel` during rendering).

## API endpoints

| endpoint | method | purpose |
|---|---|---|
| `/api/config_schema` | GET | Runtime config JSON schema (for form enums). |
| `/api/trigger_hints` | GET | Per-trigger-type scope/freigabe/EventSub hints (`TRIGGER_HINTS`). |
| `/api/commands` | GET/POST | Read/write the `triggers` list in `settings.json`. |
| `/api/settings` | GET/POST | Read/write the whole `settings.json`. |
| `/api/ports` | GET/POST | Port snapshot + per-component save. GET/POST return `oauth_redirect_uri`. |
| `/api/features` | GET/POST | Feature toggles (moderation/overlay/webui). |
| `/api/streampet` | GET/POST | `Stream_Pet.json` config (merge). |
| `/api/streampet/gifs` | GET | List of GIFs in `StreamPet/`. |
| `/api/streampet/upload` | POST | Safe GIF upload to `StreamPet/`. |
| `/api/exit` | POST | Save triggers and exit the process. |

## Display layer (`labels.js`)

The backend `TRIGGER_HINTS` keeps scope/freigabe (technical) info; the
frontend display names and matching/placeholder hints live in `labels.js`.
`displayLabel(section, key, fallback)` returns the German display string for a
technical key, falling back to the key. Structured for a future i18n swap
(i18next). `commands.js` routes all `opt.textContent = type`/`kind` sites
through `displayLabel`, so the editor shows e.g. "Chat-Befehl" instead of
"command".

`commands.js` shows:
- a matching hint for `command` (prefix + case-insensitive + args) and the
  inactivity-window/flag explanations for `new_chatter`/`first_time_chatter`;
- a live placeholder preview for `chat_reply`/`overlay_text`/`overlay_gif`
  (static sample values: `{username} → Bob`, `{args[0]} → Alice`).

## Counters (Single-Construct + Stream-Kategorie)

A counter is one trigger `!<name>` whose `reactions` is a `switch` over
`{args[0]}` with the sub-commands `+`/`-`/`set`/`reset`/`add`/`select`/`clear`/
`delsub` and `default = query`. The "+ New counter" button scaffolds this
automatically (`createNewCounter` in `commands.js`), including role-locked
cases:

- `delsub`, `reset` → `if(role:[broadcaster])` (Broadcaster-only)
- `set`, `add`, `select`, `clear` → `if(role:[mod,broadcaster])` (Mods)
- `+`, `-`, `default` (query) → free for everyone

`!<name>` (no arg) and `!<name> query` both hit the `default` case and report
the value. `amount`/`value`/`subcounter_name` are placeholder-resolved at
runtime (e.g. `!deaths + 5` → `args=["+","5"]` → `amount="{args[1]}"` resolves
to `"5"` then `int`-coerced).

### Auto-Create

A missing counter is auto-created on first use (value 0) for
`increment`/`decrement`/`set`/`reset`/`query`/`add_subcounter`/
`select_subcounter`/`clear_active_subcounter`/`delete_subcounter`. `delete`
never auto-creates (returns `counter_not_found` for a missing counter).

### `category_dependent` (Stream-Kategorie)

Each counter reaction has a `category_dependent` toggle (UI checkbox):

- **ON**: the counter `category` is the broadcaster's current Twitch stream
  `game_name` (fetched via `GET /helix/channels`, cached 60s by
  `ChannelInfoFetcher`). The counter is keyed `name:game_name`, giving
  separate values per game. Only available in production; in test/silent the
  provider returns `""` → category falls back to `"default"`.
- **OFF**: `category` is the static `category` config field (default
  `"default"`). This is NOT placeholder-resolved (it's a config value; use
  `category_dependent: true` for a dynamic category).

`renameCounter`/`deleteCounter` operate on the first `counter` reaction leaf
found in the trigger's `reactions` AST (`_counterReactionOf` walks
`seq`/`if`/`switch`).

Avoid counter names that are a prefix of another command (e.g. `!deaths` also
matches `!deathscounter` because the `command` leaf uses `startswith`).

## role-Leaf (Rollen-Check in `when` / `if.when`)

The `role` trigger-leaf checks the payload roles via `matches_roles`
(Broadcaster always passes, consistent with trigger-level roles). Empty
`roles: []` = no restriction. It is intended primarily for `if.when` inside
the reaction tree to enforce per-switch-case roles (the counter scaffolder
uses it). It is also valid in a trigger `when` tree (but the trigger-level
`roles` field usually covers that). `role` leaves contribute no EventSub
subscription type (like `compare`/`time`).

## Overlay-Positions-UI

Standalone Flask app (`src/twitchbot_runtime/overlay_pos_ui/`, port 5003,
`OVERLAY_POS_UI_PORT` overrides) editing `Stream_Pet.json` via a Drag&Drop
canvas. Position is in the `0..1` space (matches `ConfigPositionTracker`).

## Build / test

No build step is needed for the UI (plain JS). Jest tests:

```bash
cd src/UI/static
npm install
npm test
```
