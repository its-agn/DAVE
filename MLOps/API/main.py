from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from CommonUtils.json_parser import JSONParseError, JSONParser
from MLOps.Models.RF import RFClassifier

from .config import APIConfig
from .frontend_handoff import FrontendHandoff
from .repository import SwingRepository
from .swing_service import SwingService, SwingSubmissionError


config = APIConfig.from_environment()
repository = SwingRepository(config.data_root)
frontend_handoff = FrontendHandoff(config.frontend_data_root)
classifier = (
    RFClassifier.from_artifact(config.rf_artifact_path)
    if config.rf_artifact_path.is_file()
    else None
)
service = SwingService(
    config=config,
    repository=repository,
    classifier=classifier,
    frontend_handoff=frontend_handoff,
)
parser = JSONParser()

app = FastAPI(
    title="DAVE MLOps Bridge",
    version="0.1.0",
    description="Local HTTP bridge for DAVE ESP32 swing recordings.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "dave-mlops",
        "time": datetime.now(timezone.utc).isoformat(),
        "model_loaded": classifier is not None,
        "model_path": str(config.rf_artifact_path),
        "frontend_data_root": str(config.frontend_data_root),
    }


@app.post("/api/swing", status_code=status.HTTP_202_ACCEPTED)
async def receive_swing(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    body = await request.body()
    if len(body) > config.maximum_request_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Swing payload exceeds the configured request limit.",
        )
    try:
        payload = parser.parse_http_body(body)
        side, sample_count = service.validate_envelope(payload)
    except (JSONParseError, SwingSubmissionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    swing_id = uuid4().hex
    try:
        service.save_submission(swing_id, payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the incoming swing.",
        ) from exc

    background_tasks.add_task(service.process_submission, swing_id, payload)
    return {
        "accepted": True,
        "swing_id": swing_id,
        "side": side,
        "sample_count": sample_count,
        "status": "processing",
    }


@app.get("/api/swing/{swing_id}")
def get_swing(swing_id: str) -> dict[str, object]:
    result = repository.load_processed(swing_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed swing is not available.",
        )
    return result["frontend"]


@app.get("/api/swing/{swing_id}/gemini")
def get_gemini_payload(swing_id: str) -> dict[str, object]:
    result = repository.load_processed(swing_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed swing is not available.",
        )
    return result["gemini"]
