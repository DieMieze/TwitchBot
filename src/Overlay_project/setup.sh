#!/bin/bash

echo "📦 Initialisiere Overlay-Umgebung..."

# Navigiere ins Projektverzeichnis
cd "$(dirname "$0")"

# Abhängigkeiten installieren
echo "📥 Installiere npm-Abhängigkeiten..."
npm install

# Webpack ausführen
echo "🔧 Baue Overlay..."
npm run build

# Erfolgsmeldung
echo "✅ Overlay-Build abgeschlossen: static/dist/overlay.bundle.js"
