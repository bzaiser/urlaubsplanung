#!/bin/bash

# 1. Pfad-Erkennung
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Definition der Pfade
SOURCE_DIR="/volumeUSB1/usbshare/urlaubsplanung_daten"
TARGET_DIR="/volume1/daten/backup"

echo "--- Backup-Prozess gestartet ---"
echo "Skript-Pfad: $SCRIPT_PATH"
echo "Erkanntes Projekt-Verzeichnis: $PROJECT_ROOT"

# Stelle sicher, dass der Zielordner existiert
mkdir -p "$TARGET_DIR"

# 2. Suche nach der .env Datei (mit Fallbacks für Synology)
ENV_FILE=""
if [ -f "$PROJECT_ROOT/.env" ]; then
    ENV_FILE="$PROJECT_ROOT/.env"
elif [ -f "/volume1/docker/urlaubsplanung/.env" ]; then
    ENV_FILE="/volume1/docker/urlaubsplanung/.env"
elif [ -f "/volumeUSB1/usbshare/urlaubsplanung/.env" ]; then
    ENV_FILE="/volumeUSB1/usbshare/urlaubsplanung/.env"
fi

if [ -n "$ENV_FILE" ]; then
    echo "Sichere Konfiguration: $ENV_FILE -> $TARGET_DIR/urlaubsplanung.env"
    cp "$ENV_FILE" "$TARGET_DIR/urlaubsplanung.env"
else
    echo "FEHLER: .env Datei konnte an keinem Ort gefunden werden!"
fi

# 3. Inkrementelles Backup der Daten
if command -v rsync >/dev/null 2>&1; then
    echo "Verwende rsync für das Daten-Backup..."
    rsync -avu "$SOURCE_DIR" "$TARGET_DIR"
else
    echo "rsync nicht gefunden, nutze cp..."
    cp -ruv "$SOURCE_DIR" "$TARGET_DIR"
fi

echo "--- Backup erfolgreich abgeschlossen ---"
