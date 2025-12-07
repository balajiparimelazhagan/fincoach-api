#!/bin/bash
set -e

echo "Waiting for database to be ready..."
python /usr/app/scripts/wait_for_db.py

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn app.main:app --workers 1 --host 0.0.0.0 --port 8000

