#!/usr/bin/env bash
# TwitchBot launcher menu. Requires a populated .venv in the project root.
# If .venv is missing, prints a setup hint and exits (no auto-setup here).

set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$PROJECT_ROOT/.venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
    echo "[start] No virtualenv found at .venv/bin/python."
    echo "[start] Create one first:"
    echo "    python3 -m venv .venv"
    echo "    .venv/bin/pip install -r requirements-dev.txt"
    exit 1
fi

menu() {
    echo
    echo "TwitchBot - choose an option:"
    echo "  1) Config-UI starten        (port aus settings.json runtime.webui.port)"
    echo "  2) Overlay-Positions-UI     (port aus settings.json runtime.pos_ui.port)"
    echo "  3) Bot starten              (--mode production)"
    echo "  4) Tests ausfuehren"
    echo "  q) Beenden"
    printf "Selection: "
    read -r choice
    case "$choice" in
        1) config_ui ;;
        2) pos_ui ;;
        3) bot ;;
        4) tests ;;
        q|Q) exit 0 ;;
        *) echo "[start] Invalid selection." ;;
    esac
    menu
}

config_ui() {
    PYTHONPATH=src "$VENV_PY" "$PROJECT_ROOT/src/UI/Backend/UI.py"
}

pos_ui() {
    PYTHONPATH=src "$VENV_PY" -m twitchbot_runtime.overlay_pos_ui
}

bot() {
    PYTHONPATH=src "$VENV_PY" -m twitchbot_runtime --mode production
}

tests() {
    bash "$PROJECT_ROOT/scripts/run_all_tests.sh"
}

menu
