#!/bin/bash
set -e

echo "=== Geo Platform API ==="

echo "Running meta database migrations..."
alembic -x db=meta upgrade meta@head

echo "Running features database migrations..."
alembic -x db=features upgrade features@head

echo "Starting API on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
