#!/usr/bin/env bash
# Run all TwitchBot tests. Python tests are the blocking step; Node steps
# (UI Jest, Overlay build) skip with a warning if npm is not available.
# Exit code is non-zero only when Python tests fail.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== Python tests (pytest) ==="
python -m pytest -q
py_rc=$?
if [ "$py_rc" -ne 0 ]; then
    echo "[run_all_tests] Python tests FAILED (exit $py_rc)."
    exit "$py_rc"
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "[run_all_tests] npm not found — skipping UI Jest and Overlay build steps."
    exit 0
fi

set +e

echo "=== UI Jest tests ==="
(
    cd "src/UI/static"
    npm ci
    rc=$?
    [ $rc -ne 0 ] && { echo "[run_all_tests] npm ci failed in src/UI/static"; exit 1; }
    npm test
    rc=$?
    [ $rc -ne 0 ] && { echo "[run_all_tests] UI Jest tests FAILED."; exit 1; }
    exit 0
)
rc=$?
if [ "$rc" -ne 0 ]; then
    exit "$rc"
fi

echo "=== Overlay JS build ==="
(
    cd "src/Overlay_project"
    npm ci
    rc=$?
    [ $rc -ne 0 ] && { echo "[run_all_tests] npm ci failed in src/Overlay_project"; exit 1; }
    npm run build
    rc=$?
    [ $rc -ne 0 ] && { echo "[run_all_tests] Overlay build FAILED."; exit 1; }
    exit 0
)
rc=$?
if [ "$rc" -ne 0 ]; then
    exit "$rc"
fi

echo "[run_all_tests] All tests passed."
exit 0
