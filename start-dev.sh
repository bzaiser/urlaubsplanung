#!/bin/bash

echo "Starting Urlaubsplaner in Development Mode on Port 8001..."

# Ensure migrations and translations are up to date
docker-compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations travel
docker-compose -f docker-compose.dev.yml run --rm web python manage.py migrate
docker-compose -f docker-compose.dev.yml run --rm web python manage.py compilemessages

# Start the container
docker-compose -f docker-compose.dev.yml up
