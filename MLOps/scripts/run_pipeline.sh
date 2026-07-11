#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

MODE="system"
if [[ $# -gt 0 ]]; then
    if [[ "$1" == "--mode" && $# -ge 2 ]]; then
        MODE="$2"
        shift 2
    else
        echo "Usage: $0 [--mode system|database]" >&2
        exit 2
    fi
fi
if [[ $# -gt 0 || ( "$MODE" != "system" && "$MODE" != "database" ) ]]; then
    echo "Usage: $0 [--mode system|database]" >&2
    exit 2
fi

echo "Starting the persistent DAVE pipeline"
if [[ "$MODE" == "database" ]]; then
    echo "Mode: database (ESP32 -> raw archive -> label-ready motion profile)"
    echo "Training records: MLOps/Database/training"
else
    echo "Mode: system (ESP32 -> preprocessing -> model -> postprocessing -> DAVE Website/data)"
fi
echo "The service will continue handling swings until stopped with Ctrl+C."

export DAVE_PIPELINE_MODE="$MODE"
exec "$SCRIPT_DIR/run_backend.sh"
