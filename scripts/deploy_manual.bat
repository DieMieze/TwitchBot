@echo off
REM Manual deployment pipeline for TwitchBot. Idempotent: prepares a clean
REM checkout for running (venv + deps, overlay build, settings seed, smoke
REM check). Node steps skip with a warning when npm is missing.
setlocal EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_ROOT=%SCRIPT_DIR%\.."
pushd "%PROJECT_ROOT%"

echo === 1/6 venv + Python deps ===
if not exist ".venv" (
    echo [deploy_manual] creating .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [deploy_manual] venv creation FAILED.
        popd
        exit /b 1
    )
)
if exist ".venv\Scripts\pip.exe" (
    ".venv\Scripts\pip.exe" install -r requirements-dev.txt
) else (
    pip install -r requirements-dev.txt
)
if errorlevel 1 (
    echo [deploy_manual] pip install FAILED.
    popd
    exit /b 1
)

echo === 2/6 Overlay JS build ===
where npm >nul 2>&1
if errorlevel 1 (
    echo [deploy_manual] npm not found - skipping Overlay build.
    goto ui_deps
)
pushd "src\Overlay_project"
call npm ci
if errorlevel 1 goto ov_ci_failed
call npm run build
if errorlevel 1 goto ov_build_failed
popd

:ui_deps
echo === 3/6 UI deps (for tests) ===
where npm >nul 2>&1
if errorlevel 1 (
    echo [deploy_manual] npm not found - skipping UI deps.
    goto seed
)
pushd "src\UI\static"
call npm ci
if errorlevel 1 (
    echo [deploy_manual] UI dep install failed (non-blocking).
)
popd

:seed
echo === 4/6 seed settings.json ===
if not exist "settings.json" (
    copy "docs\settings.example.json" "settings.json" >nul
    echo [deploy_manual] seeded settings.json from docs\settings.example.json.
) else (
    echo [deploy_manual] settings.json already present - leaving untouched.
)

echo === 5/6 smoke check (--show-settings) ===
set "PYTHONPATH=src"
python -m twitchbot_runtime --show-settings >nul 2>&1
if errorlevel 1 (
    echo [deploy_manual] smoke check FAILED (settings did not load).
    popd
    exit /b 1
)
echo [deploy_manual] settings load OK.

echo === 6/6 next steps ===
echo Next steps:
echo   1. Configure Twitch credentials (.env) via: python scripts\get_all_scopes.py
echo   2. Set runtime.execution_mode in settings.json (silent first, then production).
echo   3. Run: start.bat  (or: python -m twitchbot_runtime --mode production)
echo [deploy_manual] done.
popd
exit /b 0

:ov_ci_failed
echo [deploy_manual] npm ci failed in src\Overlay_project
popd
popd
exit /b 1

:ov_build_failed
echo [deploy_manual] Overlay build FAILED.
popd
popd
exit /b 1
