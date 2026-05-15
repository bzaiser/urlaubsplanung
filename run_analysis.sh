#!/bin/bash

# Find the directory of this script
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

# Change to the project root (where docker-compose.yml is)
cd "$SCRIPT_DIR"

# Run the tracking analysis inside the container
# We use -T for non-interactive mode (important for cron/scheduler)
docker-compose exec -T web python manage.py run_tracking_analysis
