#!/usr/bin/env bash

set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/_common.sh"

DATASET_DIR="${1:-$MLOPS_ROOT/Database/training}"
if [[ $# -gt 0 ]]; then
    shift
fi

if [[ ! -d "$DATASET_DIR" ]]; then
    echo "RF training dataset directory does not exist: $DATASET_DIR" >&2
    echo "Usage: $0 [dataset-directory] [additional train options]" >&2
    exit 1
fi

exec "$PYTHON" -m MLOps.Models.RF.train \
    --dataset-dir "$DATASET_DIR" \
    "$@"
