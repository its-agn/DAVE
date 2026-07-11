#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
    echo "The 'uv' command is required but is not installed." >&2
    exit 1
fi

echo "Synchronizing the MLOps environment..."
uv sync --project "$REPO_ROOT/MLOps"
echo "Environment ready: $REPO_ROOT/MLOps/.venv"
