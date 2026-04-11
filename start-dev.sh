#!/bin/bash

echo "Starting Urlaubsplaner in Development Mode on Port 8001..."

# Ensure migrations are up to date
docker-compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations
docker-compose -f docker-compose.dev.yml run --rm web python manage.py migrate

# Start the container
docker-compose -f docker-compose.dev.yml up
