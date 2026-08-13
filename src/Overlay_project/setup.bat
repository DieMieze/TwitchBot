@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

echo 📦 Initialisiere Overlay-Umgebung...

REM Navigiere ins Skriptverzeichnis
cd /d %~dp0

echo 📥 Installiere npm-Abhängigkeiten...
call npm install
IF %ERRORLEVEL% NEQ 0 (
    echo ❌ Fehler bei "npm install"
    exit /b %ERRORLEVEL%
)

echo 🔧 Baue Overlay...
call npm run build
IF %ERRORLEVEL% NEQ 0 (
    echo ❌ Fehler beim Webpack-Build
    exit /b %ERRORLEVEL%
)

echo ✅ Overlay-Build abgeschlossen: static\dist\overlay.bundle.js
