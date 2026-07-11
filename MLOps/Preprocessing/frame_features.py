from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import ArmGeometry
from .models import Vector3
from .synchronizer import SynchronizedFrame


class FrameFeatureError(ValueError):
    """Raised when frame-level features cannot be calculated."""


@dataclass(frozen=True, slots=True)
class FrameFeatures:
    """Replay and motion features for one synchronized frame."""

    timestamp_ns: int
    elapsed_s: float

    upper_arm_direction: Vector3
    forearm_direction: Vector3

    shoulder_position_m: Vector3
    elbow_position_m: Vector3
    wrist_position_m: Vector3

    elbow_angle_deg: float
    elbow_angular_velocity_dps: float
    elbow_angular_acceleration_dps2: float

    upper_arm_gyro_magnitude_rads: float
    forearm_gyro_magnitude_rads: float
    relative_gyro_magnitude_rads: float

    upper_arm_linear_accel_magnitude_mps2: float
    forearm_linear_accel_magnitude_mps2: float

    wrist_speed_mps: float

    @property
    def timestamp_s(self) -> float:
        return self.timestamp_ns / 1_000_000_000

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp_s": self.timestamp_s,
            "elapsed_s": self.elapsed_s,
            "upper_arm_direction": self.upper_arm_direction.as_dict(),
            "forearm_direction": self.forearm_direction.as_dict(),
            "joints_m": {
                "shoulder": self.shoulder_position_m.as_dict(),
                "elbow": self.elbow_position_m.as_dict(),
                "wrist": self.wrist_position_m.as_dict(),
            },
            "elbow_angle_deg": self.elbow_angle_deg,
            "elbow_angular_velocity_dps": (
                self.elbow_angular_velocity_dps
            ),
            "elbow_angular_acceleration_dps2": (
                self.elbow_angular_acceleration_dps2
            ),
            "upper_arm_gyro_magnitude_rads": (
                self.upper_arm_gyro_magnitude_rads
            ),
            "forearm_gyro_magnitude_rads": (
                self.forearm_gyro_magnitude_rads
            ),
            "relative_gyro_magnitude_rads": (
                self.relative_gyro_magnitude_rads
            ),
            "upper_arm_linear_accel_magnitude_mps2": (
                self.upper_arm_linear_accel_magnitude_mps2
            ),
            "forearm_linear_accel_magnitude_mps2": (
                self.forearm_linear_accel_magnitude_mps2
            ),
            "wrist_speed_mps": self.wrist_speed_mps,
        }


class FrameFeatureExtractor:
    """Calculates frame-level features for a complete swing."""

    def extract(
        self,
        frames: tuple[SynchronizedFrame, ...],
        geometries: tuple[ArmGeometry, ...],
    ) -> tuple[FrameFeatures, ...]:
        if len(frames) != len(geometries):
            raise FrameFeatureError(
                "Synchronized frames and geometries must have "
                "the same length."
            )

        if len(frames) < 2:
            raise FrameFeatureError(
                "At least two frames are required."
            )

        for index, (frame, geometry) in enumerate(
            zip(frames, geometries)
        ):
            if frame.timestamp_ns != geometry.timestamp_ns:
                raise FrameFeatureError(
                    f"Timestamp mismatch at frame {index}."
                )

        elbow_angles = tuple(
            geometry.elbow_angle_deg for geometry in geometries
        )
        wrist_positions = tuple(
            geometry.joints.wrist for geometry in geometries
        )
        timestamps = tuple(
            frame.timestamp_ns for frame in frames
        )

        elbow_velocities = self._differentiate_scalars(
            values=elbow_angles,
            timestamps_ns=timestamps,
        )
        elbow_accelerations = self._differentiate_scalars(
            values=elbow_velocities,
            timestamps_ns=timestamps,
        )
        wrist_speeds = self._differentiate_positions(
            positions=wrist_positions,
            timestamps_ns=timestamps,
        )

        start_ns = timestamps[0]
        results: list[FrameFeatures] = []

        for index, (frame, geometry) in enumerate(
            zip(frames, geometries)
        ):
            upper_gyro = frame.shoulder.gyro_rads
            forearm_gyro = frame.forearm.gyro_rads

            relative_gyro = Vector3(
                x=forearm_gyro.x - upper_gyro.x,
                y=forearm_gyro.y - upper_gyro.y,
                z=forearm_gyro.z - upper_gyro.z,
            )

            results.append(
                FrameFeatures(
                    timestamp_ns=frame.timestamp_ns,
                    elapsed_s=(
                        frame.timestamp_ns - start_ns
                    ) / 1_000_000_000,
                    upper_arm_direction=(
                        geometry.upper_arm_direction
                    ),
                    forearm_direction=(
                        geometry.forearm_direction
                    ),
                    shoulder_position_m=(
                        geometry.joints.shoulder
                    ),
                    elbow_position_m=geometry.joints.elbow,
                    wrist_position_m=geometry.joints.wrist,
                    elbow_angle_deg=geometry.elbow_angle_deg,
                    elbow_angular_velocity_dps=(
                        elbow_velocities[index]
                    ),
                    elbow_angular_acceleration_dps2=(
                        elbow_accelerations[index]
                    ),
                    upper_arm_gyro_magnitude_rads=(
                        self._magnitude(upper_gyro)
                    ),
                    forearm_gyro_magnitude_rads=(
                        self._magnitude(forearm_gyro)
                    ),
                    relative_gyro_magnitude_rads=(
                        self._magnitude(relative_gyro)
                    ),
                    upper_arm_linear_accel_magnitude_mps2=(
                        self._magnitude(
                            frame.shoulder.linear_accel_mps2
                        )
                    ),
                    forearm_linear_accel_magnitude_mps2=(
                        self._magnitude(
                            frame.forearm.linear_accel_mps2
                        )
                    ),
                    wrist_speed_mps=wrist_speeds[index],
                )
            )

        return tuple(results)

    def _differentiate_scalars(
        self,
        values: tuple[float, ...],
        timestamps_ns: tuple[int, ...],
    ) -> tuple[float, ...]:
        """
        Differentiate values using forward/backward differences at the
        endpoints and central differences inside the recording.
        """
        derivatives: list[float] = []

        for index in range(len(values)):
            first_index, second_index = self._difference_indices(
                index=index,
                count=len(values),
            )

            dt_s = (
                timestamps_ns[second_index]
                - timestamps_ns[first_index]
            ) / 1_000_000_000

            if dt_s <= 0:
                raise FrameFeatureError(
                    "Frame timestamps must be strictly increasing."
                )

            derivative = (
                values[second_index] - values[first_index]
            ) / dt_s

            derivatives.append(derivative)

        return tuple(derivatives)

    def _differentiate_positions(
        self,
        positions: tuple[Vector3, ...],
        timestamps_ns: tuple[int, ...],
    ) -> tuple[float, ...]:
        speeds: list[float] = []

        for index in range(len(positions)):
            first_index, second_index = self._difference_indices(
                index=index,
                count=len(positions),
            )

            dt_s = (
                timestamps_ns[second_index]
                - timestamps_ns[first_index]
            ) / 1_000_000_000

            if dt_s <= 0:
                raise FrameFeatureError(
                    "Frame timestamps must be strictly increasing."
                )

            first = positions[first_index]
            second = positions[second_index]

            displacement = Vector3(
                x=second.x - first.x,
                y=second.y - first.y,
                z=second.z - first.z,
            )

            speeds.append(
                self._magnitude(displacement) / dt_s
            )

        return tuple(speeds)

    @staticmethod
    def _difference_indices(
        index: int,
        count: int,
    ) -> tuple[int, int]:
        if index == 0:
            return 0, 1

        if index == count - 1:
            return count - 2, count - 1

        return index - 1, index + 1

    @staticmethod
    def _magnitude(vector: Vector3) -> float:
        return math.sqrt(
            vector.x * vector.x
            + vector.y * vector.y
            + vector.z * vector.z
        )