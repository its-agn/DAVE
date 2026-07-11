from __future__ import annotations

import math
from dataclasses import dataclass

from .frame_features import FrameFeatures
from .synchronizer import SynchronizedFrame


class TemporalFeatureError(ValueError):
    """Raised when temporal model features cannot be constructed."""


@dataclass(frozen=True, slots=True)
class TemporalFeatureSet:
    """A time-ordered feature matrix and its schema."""

    schema_version: str
    feature_names: tuple[str, ...]
    timestamps_ns: tuple[int, ...]
    values: tuple[tuple[float, ...], ...]

    @property
    def frame_count(self) -> int:
        return len(self.values)

    @property
    def feature_count(self) -> int:
        return len(self.feature_names)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "feature_names": list(self.feature_names),
            "timestamps_s": [
                timestamp / 1_000_000_000
                for timestamp in self.timestamps_ns
            ],
            "values": [
                list(row)
                for row in self.values
            ],
        }


class TemporalFeatureBuilder:
    """
    Builds the temporal feature matrix used by the 1D CNN.

    This class does not normalize, pad, resample, or augment the matrix.
    Those operations must be fitted or configured in the model pipeline.
    """

    SCHEMA_VERSION = "1.0.0"

    FEATURE_NAMES = (
        # Forearm: IMU 1
        "forearm_accel_x_mps2",
        "forearm_accel_y_mps2",
        "forearm_accel_z_mps2",
        "forearm_gyro_x_rads",
        "forearm_gyro_y_rads",
        "forearm_gyro_z_rads",
        "forearm_linear_accel_x_mps2",
        "forearm_linear_accel_y_mps2",
        "forearm_linear_accel_z_mps2",

        # Upper arm: IMU 2
        "upper_arm_accel_x_mps2",
        "upper_arm_accel_y_mps2",
        "upper_arm_accel_z_mps2",
        "upper_arm_gyro_x_rads",
        "upper_arm_gyro_y_rads",
        "upper_arm_gyro_z_rads",
        "upper_arm_linear_accel_x_mps2",
        "upper_arm_linear_accel_y_mps2",
        "upper_arm_linear_accel_z_mps2",

        # Reconstructed segment directions
        "upper_arm_direction_x",
        "upper_arm_direction_y",
        "upper_arm_direction_z",
        "forearm_direction_x",
        "forearm_direction_y",
        "forearm_direction_z",

        # Elbow motion
        "elbow_angle_deg",
        "elbow_angular_velocity_dps",
        "elbow_angular_acceleration_dps2",

        # Motion magnitudes
        "upper_arm_gyro_magnitude_rads",
        "forearm_gyro_magnitude_rads",
        "relative_gyro_magnitude_rads",
        "upper_arm_linear_accel_magnitude_mps2",
        "forearm_linear_accel_magnitude_mps2",

        # Shoulder-relative wrist motion
        "wrist_speed_mps",
    )

    def build(
        self,
        synchronized_frames: tuple[SynchronizedFrame, ...],
        frame_features: tuple[FrameFeatures, ...],
    ) -> TemporalFeatureSet:
        if len(synchronized_frames) != len(frame_features):
            raise TemporalFeatureError(
                "Synchronized frames and frame features must have "
                "the same length."
            )

        if not synchronized_frames:
            raise TemporalFeatureError(
                "At least one synchronized frame is required."
            )

        timestamps: list[int] = []
        rows: list[tuple[float, ...]] = []

        for index, (frame, features) in enumerate(
            zip(synchronized_frames, frame_features)
        ):
            if frame.timestamp_ns != features.timestamp_ns:
                raise TemporalFeatureError(
                    f"Timestamp mismatch at frame {index}."
                )

            row = self._build_row(frame, features)

            if len(row) != len(self.FEATURE_NAMES):
                raise TemporalFeatureError(
                    f"Frame {index} produced {len(row)} features; "
                    f"expected {len(self.FEATURE_NAMES)}."
                )

            if not all(math.isfinite(value) for value in row):
                raise TemporalFeatureError(
                    f"Frame {index} contains a non-finite feature."
                )

            timestamps.append(frame.timestamp_ns)
            rows.append(row)

        return TemporalFeatureSet(
            schema_version=self.SCHEMA_VERSION,
            feature_names=self.FEATURE_NAMES,
            timestamps_ns=tuple(timestamps),
            values=tuple(rows),
        )

    @staticmethod
    def _build_row(
        frame: SynchronizedFrame,
        features: FrameFeatures,
    ) -> tuple[float, ...]:
        forearm = frame.forearm
        upper_arm = frame.shoulder

        return (
            # Forearm raw and gravity-removed motion
            forearm.accel_mps2.x,
            forearm.accel_mps2.y,
            forearm.accel_mps2.z,
            forearm.gyro_rads.x,
            forearm.gyro_rads.y,
            forearm.gyro_rads.z,
            forearm.linear_accel_mps2.x,
            forearm.linear_accel_mps2.y,
            forearm.linear_accel_mps2.z,

            # Upper-arm raw and gravity-removed motion
            upper_arm.accel_mps2.x,
            upper_arm.accel_mps2.y,
            upper_arm.accel_mps2.z,
            upper_arm.gyro_rads.x,
            upper_arm.gyro_rads.y,
            upper_arm.gyro_rads.z,
            upper_arm.linear_accel_mps2.x,
            upper_arm.linear_accel_mps2.y,
            upper_arm.linear_accel_mps2.z,

            # Segment directions
            features.upper_arm_direction.x,
            features.upper_arm_direction.y,
            features.upper_arm_direction.z,
            features.forearm_direction.x,
            features.forearm_direction.y,
            features.forearm_direction.z,

            # Elbow motion
            features.elbow_angle_deg,
            features.elbow_angular_velocity_dps,
            features.elbow_angular_acceleration_dps2,

            # Motion magnitudes
            features.upper_arm_gyro_magnitude_rads,
            features.forearm_gyro_magnitude_rads,
            features.relative_gyro_magnitude_rads,
            features.upper_arm_linear_accel_magnitude_mps2,
            features.forearm_linear_accel_magnitude_mps2,

            # Reconstructed wrist motion
            features.wrist_speed_mps,
        )