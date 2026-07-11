#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting the persistent DAVE pipeline"
echo "ESP32 -> FastAPI -> preprocessing -> model -> postprocessing -> Website/data"
echo "The service will continue handling swings until stopped with Ctrl+C."

exec "$SCRIPT_DIR/run_backend.sh"
