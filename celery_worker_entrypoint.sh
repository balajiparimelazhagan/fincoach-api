#!/bin/bash
# Celery worker entrypoint script

set -e

echo "Waiting for Redis to be ready..."
while ! nc -z redis 6379; do
  sleep 1
done
echo "Redis is ready!"

echo "Waiting for PostgreSQL to be ready..."
python wait_for_db.py

echo "Starting Celery worker..."
exec celery -A app.celery_app worker --loglevel=info --concurrency=4 -Q email_processing,scheduling
