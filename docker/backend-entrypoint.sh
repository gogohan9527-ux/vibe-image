#!/bin/sh
set -e

CONFIG_PATH="/app/config/config.yaml"
EXAMPLE_PATH="/app/config/config.example.yaml"

if [ ! -f "$CONFIG_PATH" ]; then
    if [ -f "$EXAMPLE_PATH" ]; then
        echo "[entrypoint] config.yaml missing, falling back to config.example.yaml"
        cp "$EXAMPLE_PATH" "$CONFIG_PATH"
    else
        echo "[entrypoint] no config available at /app/config; aborting"
        exit 1
    fi
fi

cd /app/backend

echo "[entrypoint] running init_db (idempotent)..."
python -m app.scripts.init_db

echo "[entrypoint] starting uvicorn on 0.0.0.0:8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
