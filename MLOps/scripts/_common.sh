#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
MLOPS_ROOT="$REPO_ROOT/MLOps"
PYTHON="$MLOPS_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "Missing MLOps Python environment: $PYTHON" >&2
    echo "Run: $SCRIPT_DIR/setup.sh" >&2
    exit 1
fi

cd "$REPO_ROOT"
