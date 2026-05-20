#!/bin/sh
set -e

echo "[entrypoint] Running Alembic migrations..."
if ! alembic upgrade head; then
    echo "[entrypoint] ERROR: Alembic migrations failed. Exiting."
    exit 1
fi

echo "[entrypoint] Migrations complete. Starting server."
exec uvicorn src.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" "$@"
