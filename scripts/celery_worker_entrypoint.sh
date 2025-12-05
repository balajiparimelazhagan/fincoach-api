#!/bin/bash
# Celery worker entrypoint script

set -e

echo "Waiting for Redis to be ready..."
while ! nc -z redis 6379; do
  sleep 1
done
echo "Redis is ready!"

echo "Waiting for PostgreSQL to be ready..."
python /usr/app/scripts/wait_for_db.py

echo "Waiting for API to be ready (poll /health)..."
until python - <<'PY'
import sys, http.client
try:
    conn = http.client.HTTPConnection('api', 8000, timeout=2)
    conn.request('GET', '/health')
    resp = conn.getresponse()
    sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
PY
do
  echo "API not ready yet, sleeping 2s..."
  sleep 2
done
echo "API ready!"

echo "Starting Celery worker..."
exec celery -A app.celery.celery_app worker --loglevel=info --concurrency=4 -Q email_processing,scheduling
