#!/bin/bash

# Exit on any error
set -e

# Find the script's directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting FAST Update Process (No Rebuild)..."

# Move to the project root directory for all operations
cd "$ROOT_DIR"

# Pull new changes from git
echo "Pulling from git repository..."
git pull origin $(git rev-parse --abbrev-ref HEAD)

# Fix permissions
echo "Ensuring project-wide permissions..."
chmod -R a+rwX .
chmod +x manage.py

# Syncing requirements (inside running container)
echo "Syncing requirements..."
docker compose --env-file .env exec web pip install -q --no-cache-dir -r requirements.txt

# Run database migrations
echo "Database migrations..."
docker compose --env-file .env exec web python3 manage.py migrate

# Compile translations
echo "Compiling translations..."
docker compose --env-file .env exec web python3 manage.py compilemessages

# Collect static files
echo "Collecting static files..."
docker compose --env-file .env exec web python3 manage.py collectstatic --noinput

# Update/Restart the services
echo "Updating containers..."
docker compose --env-file .env up -d
docker compose --env-file .env restart web

echo "-----------------------------------"
echo "FAST Update complete! The UI/Code is now live."
