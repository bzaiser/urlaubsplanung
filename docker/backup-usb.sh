#!/bin/bash
# Finde den Projekt-Stammordner (eine Ebene über diesem Skript)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Definition der Pfade
SOURCE_DIR="/volumeUSB1/usbshare/urlaubsplanung_daten"
TARGET_DIR="/volume1/daten/backup"

echo "Starte Backup von $SOURCE_DIR nach $TARGET_DIR ..."

# Stelle sicher, dass der Zielordner existiert
mkdir -p "$TARGET_DIR"

# 1. Sicherung der .env Datei (wichtig für die Konfiguration)
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Sichere .env Konfiguration..."
    cp "$PROJECT_ROOT/.env" "$TARGET_DIR/.env_backup"
fi

# 2. Inkrementelles Backup der Daten (Datenbank & Bilder)
if command -v rsync >/dev/null 2>&1; then
    echo "Verwende rsync für das inkrementelle Backup..."
    # -a (archive), -v (verbose), -u (update)
    rsync -avu "$SOURCE_DIR" "$TARGET_DIR"
else
    echo "rsync nicht gefunden, falle auf cp zurück..."
    cp -ruv "$SOURCE_DIR" "$TARGET_DIR"
fi

echo "Backup erfolgreich abgeschlossen!"
