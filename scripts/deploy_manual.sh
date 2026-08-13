#!/usr/bin/env bash
# Manual deployment pipeline for TwitchBot. Idempotent: prepares a clean
# checkout for running (venv + deps, overlay build, settings seed, smoke check).
# Node steps skip with a warning when npm is missing.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== 1/6 venv + Python deps ==="
if [ ! -d ".venv" ]; then
    echo "[deploy_manual] creating .venv ..."
    python -m venv .venv || { echo "[deploy_manual] venv creation FAILED."; exit 1; }
fi
# Prefer the venv pip when available, fall back to the system python.
if [ -f ".venv/bin/pip" ]; then
    ".venv/bin/pip" install -r requirements-dev.txt || { echo "[deploy_manual] pip install FAILED."; exit 1; }
else
    pip install -r requirements-dev.txt || { echo "[deploy_manual] pip install FAILED."; exit 1; }
fi

echo "=== 2/6 Overlay JS build ==="
if command -v npm >/dev/null 2>&1; then
    (
        cd "src/Overlay_project"
        npm ci || { echo "[deploy_manual] npm ci failed in src/Overlay_project"; exit 1; }
        npm run build || { echo "[deploy_manual] Overlay build FAILED."; exit 1; }
    ) || exit 1
else
    echo "[deploy_manual] npm not found - skipping Overlay build."
fi

echo "=== 3/6 UI deps (for tests) ==="
if command -v npm >/dev/null 2>&1; then
    (
        cd "src/UI/static"
        npm ci || { echo "[deploy_manual] npm ci failed in src/UI/static"; exit 1; }
    ) || echo "[deploy_manual] UI dep install failed (non-blocking)."
else
    echo "[deploy_manual] npm not found - skipping UI deps."
fi

echo "=== 4/6 seed settings.json ==="
if [ ! -f "settings.json" ]; then
    cp "docs/settings.example.json" "settings.json"
    echo "[deploy_manual] seeded settings.json from docs/settings.example.json."
else
    echo "[deploy_manual] settings.json already present - leaving untouched."
fi

echo "=== 5/6 smoke check (--show-settings) ==="
PYTHONPATH=src python -m twitchbot_runtime --show-settings >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[deploy_manual] smoke check FAILED (settings did not load)."
    exit 1
fi
echo "[deploy_manual] settings load OK."

echo "=== 6/6 next steps ==="
echo "Next steps:"
echo "  1. Configure Twitch credentials (.env) via: python scripts/get_all_scopes.py"
echo "  2. Set runtime.execution_mode in settings.json (silent first, then production)."
echo "  3. Run: start.sh  (or: python -m twitchbot_runtime --mode production)"
echo "[deploy_manual] done."
exit 0
