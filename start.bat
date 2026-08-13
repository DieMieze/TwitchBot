@echo off
setlocal EnableDelayedExpansion
REM TwitchBot launcher menu. Requires a populated .venv in the project root.
REM If .venv is missing, prints a setup hint and exits (no auto-setup here).

set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "VENV_PY=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [start] No virtualenv found at ".venv\Scripts\python.exe".
    echo [start] Create one first:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements-dev.txt
    exit /b 1
)

:menu
echo.
echo TwitchBot - choose an option:
echo   1) Config-UI starten        (port aus settings.json runtime.webui.port)
echo   2) Overlay-Positions-UI    (port aus settings.json runtime.pos_ui.port)
echo   3) Bot starten             (--mode production)
echo   4) Tests ausfuehren
echo   q) Beenden
set "CHOICE="
set /p "CHOICE=Selection: "

if /i "%CHOICE%"=="1" goto config_ui
if /i "%CHOICE%"=="2" goto pos_ui
if /i "%CHOICE%"=="3" goto bot
if /i "%CHOICE%"=="4" goto tests
if /i "%CHOICE%"=="q" exit /b 0
echo [start] Invalid selection.
goto menu

:config_ui
set "PYTHONPATH=src"
"%VENV_PY%" src\UI\Backend\UI.py
set "PYTHONPATH="
goto menu

:pos_ui
set "PYTHONPATH=src"
"%VENV_PY%" -m twitchbot_runtime.overlay_pos_ui
set "PYTHONPATH="
goto menu

:bot
set "PYTHONPATH=src"
"%VENV_PY%" -m twitchbot_runtime --mode production
set "PYTHONPATH="
goto menu

:tests
call "%PROJECT_ROOT%\scripts\run_all_tests.bat"
goto menu
