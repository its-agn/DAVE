#!/usr/bin/env bash

set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/_common.sh"

if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required for the real HTTP check." >&2
    exit 1
fi

PORT="${PORT:-8765}"
TEST_DATA_ROOT="$(mktemp -d -t dave_api_http_XXXXXX)"
SERVER_LOG="$TEST_DATA_ROOT/server.log"

cleanup() {
    if [[ -n "${SERVER_PID:-}" ]]; then
        kill "$SERVER_PID" >/dev/null 2>&1 || true
        wait "$SERVER_PID" >/dev/null 2>&1 || true
    fi
    rm -rf "$TEST_DATA_ROOT"
}
trap cleanup EXIT

echo "Starting temporary API on 127.0.0.1:$PORT..."
env DAVE_DATA_ROOT="$TEST_DATA_ROOT" \
    "$PYTHON" -m uvicorn MLOps.API.main:app \
    --host 127.0.0.1 \
    --port "$PORT" \
    >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

ready=0
for _ in $(seq 1 100); do
    if curl --silent --fail \
        "http://127.0.0.1:$PORT/health" >/dev/null; then
        ready=1
        break
    fi
    sleep 0.2
done

if [[ "$ready" -ne 1 ]]; then
    echo "API did not become ready." >&2
    cat "$SERVER_LOG" >&2
    exit 1
fi

ACKNOWLEDGMENT="$TEST_DATA_ROOT/acknowledgment.json"
curl --silent --show-error --fail \
    --header "Content-Type: application/json" \
    --data-binary \
    @"$MLOPS_ROOT/Preprocessing/tests/fixtures/JSONtest_R.json" \
    "http://127.0.0.1:$PORT/api/swing" \
    >"$ACKNOWLEDGMENT"

SWING_ID="$($PYTHON -c \
    "import json; print(json.load(open('$ACKNOWLEDGMENT'))['swing_id'])")"

result_ready=0
for _ in $(seq 1 50); do
    if curl --silent --fail \
        "http://127.0.0.1:$PORT/api/swing/$SWING_ID" \
        >"$TEST_DATA_ROOT/result.json"; then
        result_ready=1
        break
    fi
    sleep 0.1
done

if [[ "$result_ready" -ne 1 ]]; then
    echo "Processed result did not become available." >&2
    cat "$SERVER_LOG" >&2
    exit 1
fi

"$PYTHON" - "$ACKNOWLEDGMENT" "$TEST_DATA_ROOT/result.json" <<'PY'
import json
import sys

acknowledgment = json.load(open(sys.argv[1]))
result = json.load(open(sys.argv[2]))

assert acknowledgment["accepted"] is True
assert acknowledgment["side"] == "R"
assert acknowledgment["sample_count"] == 5
assert result["swing_id"] == acknowledgment["swing_id"]
assert len(result["preprocessing"]["frames"]) == 5

print(
    f"PASS real HTTP: swing_id={result['swing_id']}, "
    "status=202, frames=5"
)
PY

echo "Real localhost HTTP check passed."
