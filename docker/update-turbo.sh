#!/bin/bash

# Exit on any error
set -e

# Find the script's directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 Starting TURBO Update (Design/Logic only, No Restart)..."

# Move to the project root directory
cd "$ROOT_DIR"

# Pull new changes from git
echo "⏬ Pulling from git..."
git pull origin $(git rev-parse --abbrev-ref HEAD)

# Permissions
chmod -R a+rwX .
chmod +x manage.py

# Optional: Compile translations if any changed
echo "🌍 Compiling translations..."
docker compose --env-file .env exec web python3 manage.py compilemessages

# Optional: Collect static (needed if using WhiteNoise or similar)
echo "🎨 Collecting static files..."
docker compose --env-file .env exec web python3 manage.py collectstatic --noinput

# Optional: Reset failed geocoding for a fresh attempt with improved logic
echo "🧹 Resetting failed geocoding attempts..."
docker compose --env-file .env exec web python3 manage.py shell -c "from travel.models import Day, Event; Day.objects.filter(is_geocoded=True, latitude__isnull=True).update(is_geocoded=False); Event.objects.filter(is_geocoded=True, latitude__isnull=True).update(is_geocoded=False); print('✨ Failed geocodes reset!')"

echo "-----------------------------------"
echo "⚡ TURBO Update complete! Changes should be live instantly."
