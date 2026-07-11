#!/usr/bin/env bash

set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/_common.sh"

echo "Checking FastAPI receive, persistence, and preprocessing in-process..."

"$PYTHON" -m compileall -q "$MLOPS_ROOT/API"

"$PYTHON" - <<'PY'
import asyncio
import json
import os
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request


async def make_request(body: bytes) -> Request:
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/swing",
        "raw_path": b"/api/swing",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }
    return Request(scope, receive)


async def run() -> None:
    with tempfile.TemporaryDirectory(prefix="dave_api_test_") as directory:
        os.environ["DAVE_DATA_ROOT"] = directory
        os.environ["DAVE_FRONTEND_DATA_ROOT"] = str(
            Path(directory) / "frontend"
        )

        # Import after setting DAVE_DATA_ROOT because main constructs the
        # configured repository at import time.
        from MLOps.API.main import health, receive_swing, repository, service

        fixture = Path(
            "MLOps/Preprocessing/tests/fixtures/JSONtest_R.json"
        )
        body = fixture.read_bytes()
        tasks = BackgroundTasks()
        acknowledgment = await receive_swing(
            await make_request(body),
            tasks,
        )

        assert acknowledgment["accepted"] is True
        assert acknowledgment["side"] == "R"
        assert acknowledgment["sample_count"] == 5
        assert acknowledgment["status"] == "processing"
        assert len(tasks.tasks) == 1, "Background processing was not scheduled"

        swing_id = acknowledgment["swing_id"]
        raw_path = Path(directory) / "raw" / f"{swing_id}.json"
        assert raw_path.is_file(), "Raw swing was not saved"

        # Exercise the scheduled service operation directly. This avoids
        # involving Starlette's thread pool in an in-process shell test.
        service.process_submission(
            swing_id,
            json.loads(body),
        )

        processed = repository.load_processed(swing_id)
        assert processed is not None, "Processed swing was not saved"
        assert processed["frontend"]["side"] == "R"
        assert len(processed["frontend"]["preprocessing"]["frames"]) == 5
        assert (
            len(
                processed["model_inputs"]["temporal_features"]
                ["feature_names"]
            )
            == 33
        )
        assert (
            processed["frontend"]["classification"]["status"]
            == "unavailable"
        )
        assert len(processed["gemini"]["sampled_motion"]) == 2
        assert processed["gemini"]["frame_stride"] == 25
        assert processed["gemini"]["sampled_motion"][0]["elapsed_s"] == 0.0
        assert processed["gemini"]["sampled_motion"][-1]["elapsed_s"] == 0.008

        frontend_root = Path(directory) / "frontend"
        latest = json.loads((frontend_root / "latest.json").read_text())
        assert latest["swing_id"] == swing_id
        assert (frontend_root / latest["swing_file"]).is_file()
        assert (frontend_root / latest["gemini_file"]).is_file()

        health_result = health()
        assert health_result["status"] == "ok"

        try:
            await receive_swing(
                await make_request(b'{"side":"R"}'),
                BackgroundTasks(),
            )
        except HTTPException as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError("Invalid payload was unexpectedly accepted")

        print(
            f"PASS API: swing_id={swing_id}, "
            "raw_saved=true, frames=5, temporal_features=33"
        )


asyncio.run(run())
PY

echo "In-process API checks passed."
