#!/bin/bash

# Find the directory of this script
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

# LOAD PATHS (Essential for Synology Task Scheduler)
export PATH=/usr/local/bin:/usr/bin:/bin:/snap/bin:$PATH

# Change to the project root (where docker-compose.yml is)
cd "$SCRIPT_DIR"

# Run the tracking analysis inside the container
# We try both docker-compose and docker compose to be safe
if command -v docker-compose &> /dev/null; then
    docker-compose exec -T web python manage.py run_tracking_analysis
else
    docker compose exec -T web python manage.py run_tracking_analysis
fi
