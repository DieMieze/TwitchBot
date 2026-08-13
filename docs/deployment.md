# Deployment

TwitchBot is a Python package plus a browser overlay; there is no server-side
deploy beyond running the runtime. This page covers the **manual deployment
pipeline** (local script + manually triggered GitHub workflow) used to produce
a publishing-ready artifact. For the automated release tarball (venv bundle),
see `.github/workflows/release.yml`.

## Prerequisites

- Python 3.10+ (CI uses 3.11)
- Node 22 LTS (for the overlay JS bundle and UI Jest tests)
- `cloudflared` on PATH (production only — the runtime starts a Quick Tunnel)
- A registered Twitch app (client id/secret) with the OAuth redirect URI
  `http://localhost:5003/oauth/callback` registered (see
  [../README.md](../README.md) → "Twitch app registration & OAuth setup")

## Manual local pipeline (`scripts/deploy_manual.*`)

Idempotent Windows (`.bat`) and Linux (`.sh`) scripts that prepare a clean
checkout for running:

1. Create/verify `.venv`, install `requirements-dev.txt`.
2. `cd src/Overlay_project && npm ci && npm run build` (skip with warning if
   `npm` is missing).
3. `cd src/UI/static && npm ci` (only for tests; skip if `npm` is missing).
4. Copy `docs/settings.example.json` → `settings.json` if not already present
   (never overwrites).
5. Smoke-check: `python -m twitchbot_runtime --show-settings`.
6. Print the next steps (configure `.env` via `scripts/get_all_scopes.py`, set
   `runtime.execution_mode`, run `start.bat`/`start.sh`).

```bash
scripts/deploy_manual.sh   # Linux
scripts\deploy_manual.bat  # Windows
```

## Manual GitHub workflow (`.github/workflows/deploy-manual.yml`)

A `workflow_dispatch`-triggered workflow (optional `os` input:
`windows`/`ubuntu`) that builds a wheel and uploads it with the overlay bundle
as release artifacts. **No** automatic push/release — only artifact
preparation for publishing.

Trigger: GitHub → Actions → "Deploy (manual)" → Run workflow.

Steps: checkout → Python 3.11 → Node 22 → venv + deps → overlay build →
`python -m build` (wheel) → upload wheel + `overlay.bundle.js`.

This is a parallel track to `release.yml` (which bundles a venv tarball on
`v*` tags / `workflow_dispatch`); `deploy-manual.yml` is for an on-demand
publishing-ready build without a tag trigger.

## First run (after deploy)

1. Configure Twitch credentials in `.env`:

   ```bash
   python scripts/get_all_scopes.py            # both accounts
   python scripts/get_all_scopes.py --bot-only # just the bot
   ```

   The script prints the exact redirect URI to register in the Twitch Developer
   Console (must match `http://localhost:5003/oauth/callback` by default).

2. Set `runtime.execution_mode` in `settings.json` (`silent` to capture
   events first, `production` for full operation).
3. Run the launcher:

   ```bash
   start.bat   # Windows
   ./start.sh  # Linux
   ```

   Or directly:

   ```bash
   python -m twitchbot_runtime --mode production
   ```

## Smoke test

After deploy + first run, verify:

- `python -m twitchbot_runtime --show-settings` loads settings without error.
- The Config-UI (`runtime.webui.port`, default 5001) opens and shows triggers,
  ports (with the copyable OAuth redirect URI), and features.
- In test mode the REPL accepts events (`chat.message`, etc.).

## Troubleshooting

| symptom | cause / fix |
|---|---|
| `PortInUseError: port 5000 on 127.0.0.1 is already in use` | Another process holds the port; the error prints free alternatives. Set `runtime.<component>.port` in `settings.json` or the Config-UI Ports section. |
| `400 redirect_uri_mismatch` during OAuth | The Twitch Console OAuth Redirect URI does not match `http://localhost:<oauth.port>/oauth/callback`. Register the exact URI the script prints (and the Config-UI shows). |
| EventSub subscription registration fails | The cloudflared tunnel did not start, or `twitch.webhook_secret` is missing. Production needs a complete `.env` and the bot must be a moderator of the channel. |
| Overlay does not start | `features.overlay.enabled` must be `true` AND mode in (production, test). `silent` never starts the overlay backend. |
