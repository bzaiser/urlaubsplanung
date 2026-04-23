#!/bin/bash

# Robuste Pfad-Erkennung (funktioniert in bash und sh)
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Definition der Pfade
SOURCE_DIR="/volumeUSB1/usbshare/urlaubsplanung_daten"
TARGET_DIR="/volume1/daten/backup"

echo "Starte Backup-Prozess..."
echo "Projekt-Verzeichnis: $PROJECT_ROOT"

# Stelle sicher, dass der Zielordner existiert
mkdir -p "$TARGET_DIR"

# 1. Sicherung der .env Datei (wichtig!)
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Sichere .env Konfiguration von $PROJECT_ROOT/.env ..."
    cp "$PROJECT_ROOT/.env" "$TARGET_DIR/.env_backup"
else
    echo "WARNUNG: .env Datei nicht in $PROJECT_ROOT gefunden!"
fi

# 2. Inkrementelles Backup der Daten
if command -v rsync >/dev/null 2>&1; then
    echo "Verwende rsync für das Backup nach $TARGET_DIR ..."
    rsync -avu "$SOURCE_DIR" "$TARGET_DIR"
else
    echo "rsync nicht gefunden, falle auf cp zurück..."
    cp -ruv "$SOURCE_DIR" "$TARGET_DIR"
fi

echo "Backup erfolgreich abgeschlossen!"
