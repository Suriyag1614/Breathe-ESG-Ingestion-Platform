#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

echo "Running database migrations..."
python manage.py migrate

echo "Seeding demo enterprise data..."
python manage.py seed_demo

echo "Starting Gunicorn application server..."
exec gunicorn breathe.wsgi:application --bind 0.0.0.0:8000