#!/bin/bash

# Exit on any error
set -e

# Find the script's directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting Update Process (REBUILD)..."

# Move to the project root directory for all operations
cd "$ROOT_DIR"

# Pull new changes from git
echo "Pulling from git repository..."
git pull origin $(git rev-parse --abbrev-ref HEAD)

# Fix permissions for the Docker user
echo "Ensuring project-wide permissions..."
chmod -R a+rwX .
chmod +x manage.py

# Rebuild the docker image (fast since it uses cache)
echo "Building the docker image..."
docker compose --env-file .env build

# Start the container in detached mode
echo "Starting the container..."
docker compose --env-file .env up -d

# Syncing requirements inside container
echo "Syncing requirements..."
docker compose --env-file .env exec web pip install -q --no-cache-dir -r requirements.txt

# Database migrations
echo "Database migrations..."
docker compose --env-file .env exec web python3 manage.py migrate

# Assets & Translations
echo "Processing assets..."
docker compose --env-file .env exec web python3 manage.py compilemessages
docker compose --env-file .env exec web python3 manage.py collectstatic --noinput

echo "-----------------------------------"
echo "Update complete! Application is running."
