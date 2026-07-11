from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from MLOps.Preprocessing import PreprocessingPipeline
from MLOps.Postprocessing import FrontendResponseAssembler

from .config import APIConfig
from .repository import SwingRepository


class SwingSubmissionError(ValueError):
    """Raised when an incoming hardware envelope is invalid."""


class SwingService:
    """Validates, stores, and preprocesses ESP32 swing submissions."""

    def __init__(
        self,
        config: APIConfig,
        repository: SwingRepository,
        pipeline: PreprocessingPipeline | None = None,
        assembler: FrontendResponseAssembler | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.pipeline = pipeline or PreprocessingPipeline()
        self.assembler = assembler or FrontendResponseAssembler()

    @staticmethod
    def validate_envelope(payload: dict[str, Any]) -> tuple[str, int]:
        side = payload.get("side")
        if side not in ("L", "R"):
            raise SwingSubmissionError("'side' must be 'L' or 'R'.")
        for key in ("IMU 1", "IMU 2"):
            samples = payload.get(key)
            if not isinstance(samples, list) or not samples:
                raise SwingSubmissionError(f"'{key}' must be a nonempty array.")
        return side, len(payload["IMU 1"])

    def save_submission(self, swing_id: str, payload: dict[str, Any]) -> None:
        self.repository.save_raw(swing_id, payload)

    def process_submission(self, swing_id: str, payload: dict[str, Any]) -> None:
        try:
            result = self.pipeline.process(
                payload=payload,
                upper_arm_length_m=self.config.upper_arm_length_m,
                forearm_length_m=self.config.forearm_length_m,
            )
            processed_at = datetime.now(timezone.utc).isoformat()
            bundle = self.assembler.assemble(
                swing_id=swing_id,
                original_payload=payload,
                preprocessing=result,
                processed_at=processed_at,
            )
            processed = {
                "frontend": bundle.frontend,
                "gemini": bundle.gemini,
                "model_inputs": {
                    "temporal_features": result.temporal_features.as_dict(),
                },
            }
            self.repository.save_processed(swing_id, processed)
        except Exception as exc:
            self.repository.save_failure(
                swing_id,
                {
                    "swing_id": swing_id,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
