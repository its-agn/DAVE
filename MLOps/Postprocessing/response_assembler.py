from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from MLOps.Preprocessing import PreprocessingResult


class PostprocessingError(ValueError):
    """Raised when final response payloads cannot be assembled."""


@dataclass(frozen=True, slots=True)
class PostprocessingBundle:
    """Separate payloads for the website and Gemini."""

    frontend: dict[str, Any]
    gemini: dict[str, Any]


class FrontendResponseAssembler:
    """Builds full replay and compact Gemini payloads."""

    def __init__(
        self,
        gemini_frame_stride: int = 25,
        source_sample_rate_hz: float = 500.0,
    ) -> None:
        if gemini_frame_stride <= 0:
            raise ValueError("gemini_frame_stride must be positive.")
        if source_sample_rate_hz <= 0:
            raise ValueError("source_sample_rate_hz must be positive.")
        self.gemini_frame_stride = gemini_frame_stride
        self.source_sample_rate_hz = source_sample_rate_hz

    def assemble(
        self,
        swing_id: str,
        original_payload: Mapping[str, Any],
        preprocessing: PreprocessingResult,
        classification: Mapping[str, Any] | None = None,
        processed_at: str | None = None,
    ) -> PostprocessingBundle:
        if not swing_id:
            raise PostprocessingError("swing_id cannot be empty.")

        classification_payload = dict(classification or {
            "status": "unavailable",
            "reason": "No trained model has been configured.",
        })
        original = {
            "IMU 1": original_payload.get("IMU 1"),
            "IMU 2": original_payload.get("IMU 2"),
        }
        if not isinstance(original["IMU 1"], list):
            raise PostprocessingError("Original payload is missing 'IMU 1'.")
        if not isinstance(original["IMU 2"], list):
            raise PostprocessingError("Original payload is missing 'IMU 2'.")

        metadata: dict[str, Any] = {"swing_id": swing_id}
        if processed_at is not None:
            metadata["processed_at"] = processed_at

        frontend = {
            **metadata,
            "side": preprocessing.side,
            "original": original,
            "body": {
                "upper_arm_length_m": preprocessing.upper_arm_length_m,
                "forearm_length_m": preprocessing.forearm_length_m,
            },
            "preprocessing": {
                "frames": [frame.as_dict() for frame in preprocessing.frames],
                "motion_profile": preprocessing.motion_profile.as_dict(),
            },
            "classification": classification_payload,
        }

        gemini = {
            **metadata,
            "side": preprocessing.side,
            "source_sample_rate_hz": self.source_sample_rate_hz,
            "sampled_motion_rate_hz": (
                self.source_sample_rate_hz / self.gemini_frame_stride
            ),
            "frame_stride": self.gemini_frame_stride,
            "motion_profile": preprocessing.motion_profile.as_dict(),
            "classification": classification_payload,
            "sampled_motion": self._sample_motion(preprocessing),
        }

        return PostprocessingBundle(frontend=frontend, gemini=gemini)

    def _sample_motion(
        self,
        preprocessing: PreprocessingResult,
    ) -> list[dict[str, float]]:
        frame_count = len(preprocessing.frames)
        indices = list(range(0, frame_count, self.gemini_frame_stride))
        final_index = frame_count - 1
        if indices[-1] != final_index:
            indices.append(final_index)

        return [self._compact_frame(preprocessing.frames[index]) for index in indices]

    @staticmethod
    def _compact_frame(frame: Any) -> dict[str, float]:
        return {
            "timestamp_s": frame.timestamp_s,
            "elapsed_s": frame.elapsed_s,
            "elbow_angle_deg": frame.elbow_angle_deg,
            "elbow_angular_velocity_dps": frame.elbow_angular_velocity_dps,
            "elbow_angular_acceleration_dps2": (
                frame.elbow_angular_acceleration_dps2
            ),
            "upper_arm_gyro_magnitude_rads": (
                frame.upper_arm_gyro_magnitude_rads
            ),
            "forearm_gyro_magnitude_rads": frame.forearm_gyro_magnitude_rads,
            "relative_gyro_magnitude_rads": frame.relative_gyro_magnitude_rads,
            "upper_arm_linear_accel_magnitude_mps2": (
                frame.upper_arm_linear_accel_magnitude_mps2
            ),
            "forearm_linear_accel_magnitude_mps2": (
                frame.forearm_linear_accel_magnitude_mps2
            ),
            "wrist_speed_mps": frame.wrist_speed_mps,
        }
