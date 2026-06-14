#!/bin/sh
set -e

echo "Applying Alembic migrations..."
alembic upgrade head

echo "Starting Uvicorn on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
