from __future__ import annotations

from dataclasses import dataclass

from .frame_features import FrameFeatures
from .models import ArmSide
from .motion_profile import MotionProfile
from .temporal_features import TemporalFeatureSet


class PreprocessingResultError(ValueError):
    """Raised when preprocessing outputs are internally inconsistent."""


@dataclass(frozen=True, slots=True)
class PreprocessingResult:
    """
    Complete output of the preprocessing pipeline.

    The original HTTP payload is intentionally not stored here. The API or
    postprocessing layer retains it separately for the frontend response.
    """

    side: ArmSide
    upper_arm_length_m: float
    forearm_length_m: float

    frames: tuple[FrameFeatures, ...]
    motion_profile: MotionProfile
    temporal_features: TemporalFeatureSet

    def __post_init__(self) -> None:
        if self.upper_arm_length_m <= 0:
            raise PreprocessingResultError(
                "upper_arm_length_m must be positive."
            )

        if self.forearm_length_m <= 0:
            raise PreprocessingResultError(
                "forearm_length_m must be positive."
            )

        if not self.frames:
            raise PreprocessingResultError(
                "Preprocessing must produce at least one frame."
            )

        if len(self.frames) != self.temporal_features.frame_count:
            raise PreprocessingResultError(
                "Replay frames and temporal features must have "
                "the same frame count."
            )

        if (
            self.motion_profile.frame_count
            != len(self.frames)
        ):
            raise PreprocessingResultError(
                "Motion-profile frame count does not match "
                "the processed frames."
            )

        for index, (
            frame,
            temporal_timestamp,
        ) in enumerate(
            zip(
                self.frames,
                self.temporal_features.timestamps_ns,
            )
        ):
            if frame.timestamp_ns != temporal_timestamp:
                raise PreprocessingResultError(
                    f"Timestamp mismatch at frame {index}."
                )

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def duration_s(self) -> float:
        return self.motion_profile.duration_s

    def replay_dict(self) -> dict[str, object]:
        """
        Return the preprocessing values useful to the frontend replay.

        The complete temporal CNN matrix is excluded because it is an
        internal model input rather than normal frontend data.
        """
        return {
            "body": {
                "upper_arm_length_m": self.upper_arm_length_m,
                "forearm_length_m": self.forearm_length_m,
            },
            "preprocessing": {
                "frames": [
                    frame.as_dict()
                    for frame in self.frames
                ],
                "motion_profile": (
                    self.motion_profile.as_dict()
                ),
            },
        }

    def model_dict(self) -> dict[str, object]:
        """
        Return both model inputs.

        motion_profile is used by the random forest.
        temporal_features is used by the future 1D CNN.
        """
        return {
            "side": self.side,
            "motion_profile": self.motion_profile.as_dict(),
            "temporal_features": (
                self.temporal_features.as_dict()
            ),
        }