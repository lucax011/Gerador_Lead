#!/bin/sh
set -e

echo "Running database migrations..."
alembic -c shared/database/migrations/alembic.ini upgrade head

echo "Starting API..."
exec uvicorn services.api.main:app --host 0.0.0.0 --port 8000 "$@"
