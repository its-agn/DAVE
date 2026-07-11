#!/usr/bin/env bash

set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/_common.sh"

API_FILE="$MLOPS_ROOT/API/main.py"
if [[ ! -f "$API_FILE" ]]; then
    echo "Backend API has not been created yet: $API_FILE" >&2
    echo "Create MLOps/API/main.py before running this command." >&2
    exit 1
fi

if ! "$PYTHON" -c "import uvicorn" >/dev/null 2>&1; then
    echo "uvicorn is not installed in the MLOps environment." >&2
    echo "Add FastAPI and uvicorn to MLOps/pyproject.toml, then run setup.sh." >&2
    exit 1
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "Starting backend on http://$HOST:$PORT"
exec "$PYTHON" -m uvicorn MLOps.API.main:app \
    --host "$HOST" \
    --port "$PORT"
