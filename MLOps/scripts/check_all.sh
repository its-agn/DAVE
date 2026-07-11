#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/check_preprocessing.sh"
"$SCRIPT_DIR/check_rf.sh"
"$SCRIPT_DIR/check_api.sh"

echo "All available MLOps checks passed."
