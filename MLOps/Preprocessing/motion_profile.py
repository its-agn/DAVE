from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .frame_features import FrameFeatures


class MotionProfileError(ValueError):
    """Raised when a whole-swing profile cannot be calculated."""


@dataclass(frozen=True, slots=True)
class MotionProfile:
    """Fixed-length summary of one complete swing."""

    duration_s: float
    frame_count: int

    elbow_angle_min_deg: float
    elbow_angle_max_deg: float
    elbow_range_of_motion_deg: float

    peak_elbow_extension_velocity_dps: float
    peak_elbow_flexion_velocity_dps: float
    peak_elbow_angular_acceleration_dps2: float

    peak_forearm_gyro_rads: float
    peak_upper_arm_gyro_rads: float

    peak_forearm_linear_accel_mps2: float
    peak_upper_arm_linear_accel_mps2: float
    peak_wrist_speed_mps: float

    forearm_gyro_peak_time_s: float
    upper_arm_gyro_peak_time_s: float
    gyro_peak_timing_difference_ms: float

    forearm_accel_impulse_mps: float
    upper_arm_accel_impulse_mps: float

    elbow_acceleration_rms_dps2: float
    elbow_jerk_rms_dps3: float

    reached_near_full_extension: bool
    elbow_angle_below_expected_range: bool

    def as_dict(self) -> dict[str, float | int | bool]:
        return asdict(self)


class MotionProfileBuilder:
    """Builds one fixed-length feature profile from processed frames."""

    def __init__(
        self,
        near_full_extension_deg: float = 165.0,
        expected_minimum_elbow_angle_deg: float = 10.0,
    ) -> None:
        if not 0.0 <= near_full_extension_deg <= 180.0:
            raise ValueError(
                "near_full_extension_deg must be between 0 and 180."
            )

        if not 0.0 <= expected_minimum_elbow_angle_deg <= 180.0:
            raise ValueError(
                "expected_minimum_elbow_angle_deg must be "
                "between 0 and 180."
            )

        self.near_full_extension_deg = near_full_extension_deg
        self.expected_minimum_elbow_angle_deg = (
            expected_minimum_elbow_angle_deg
        )

    def build(
        self,
        frames: tuple[FrameFeatures, ...],
    ) -> MotionProfile:
        if len(frames) < 2:
            raise MotionProfileError(
                "At least two processed frames are required."
            )

        self._validate_timestamps(frames)

        elbow_angles = tuple(
            frame.elbow_angle_deg for frame in frames
        )
        elbow_velocities = tuple(
            frame.elbow_angular_velocity_dps
            for frame in frames
        )
        elbow_accelerations = tuple(
            frame.elbow_angular_acceleration_dps2
            for frame in frames
        )

        forearm_gyro = tuple(
            frame.forearm_gyro_magnitude_rads
            for frame in frames
        )
        upper_arm_gyro = tuple(
            frame.upper_arm_gyro_magnitude_rads
            for frame in frames
        )

        forearm_accel = tuple(
            frame.forearm_linear_accel_magnitude_mps2
            for frame in frames
        )
        upper_arm_accel = tuple(
            frame.upper_arm_linear_accel_magnitude_mps2
            for frame in frames
        )

        timestamps_ns = tuple(
            frame.timestamp_ns for frame in frames
        )

        forearm_peak_index = self._maximum_index(forearm_gyro)
        upper_arm_peak_index = self._maximum_index(upper_arm_gyro)

        forearm_peak_time_s = frames[
            forearm_peak_index
        ].elapsed_s
        upper_arm_peak_time_s = frames[
            upper_arm_peak_index
        ].elapsed_s

        elbow_jerk = self._differentiate(
            elbow_accelerations,
            timestamps_ns,
        )

        minimum_angle = min(elbow_angles)
        maximum_angle = max(elbow_angles)

        return MotionProfile(
            duration_s=(
                timestamps_ns[-1] - timestamps_ns[0]
            ) / 1_000_000_000,
            frame_count=len(frames),

            elbow_angle_min_deg=minimum_angle,
            elbow_angle_max_deg=maximum_angle,
            elbow_range_of_motion_deg=(
                maximum_angle - minimum_angle
            ),

            # Positive elbow velocity means extension.
            peak_elbow_extension_velocity_dps=max(
                0.0,
                max(elbow_velocities),
            ),

            # Negative elbow velocity means flexion. Store its magnitude.
            peak_elbow_flexion_velocity_dps=max(
                0.0,
                -min(elbow_velocities),
            ),

            peak_elbow_angular_acceleration_dps2=max(
                abs(value) for value in elbow_accelerations
            ),

            peak_forearm_gyro_rads=max(forearm_gyro),
            peak_upper_arm_gyro_rads=max(upper_arm_gyro),

            peak_forearm_linear_accel_mps2=max(forearm_accel),
            peak_upper_arm_linear_accel_mps2=max(upper_arm_accel),
            peak_wrist_speed_mps=max(
                frame.wrist_speed_mps for frame in frames
            ),

            forearm_gyro_peak_time_s=forearm_peak_time_s,
            upper_arm_gyro_peak_time_s=upper_arm_peak_time_s,
            gyro_peak_timing_difference_ms=(
                forearm_peak_time_s - upper_arm_peak_time_s
            ) * 1_000,

            forearm_accel_impulse_mps=self._trapezoidal_integral(
                forearm_accel,
                timestamps_ns,
            ),
            upper_arm_accel_impulse_mps=self._trapezoidal_integral(
                upper_arm_accel,
                timestamps_ns,
            ),

            elbow_acceleration_rms_dps2=self._rms(
                elbow_accelerations
            ),
            elbow_jerk_rms_dps3=self._rms(elbow_jerk),

            reached_near_full_extension=(
                maximum_angle >= self.near_full_extension_deg
            ),
            elbow_angle_below_expected_range=(
                minimum_angle
                < self.expected_minimum_elbow_angle_deg
            ),
        )

    @staticmethod
    def _validate_timestamps(
        frames: tuple[FrameFeatures, ...],
    ) -> None:
        for previous, current in zip(frames, frames[1:]):
            if current.timestamp_ns <= previous.timestamp_ns:
                raise MotionProfileError(
                    "Frame timestamps must be strictly increasing."
                )

    @staticmethod
    def _maximum_index(values: tuple[float, ...]) -> int:
        return max(
            range(len(values)),
            key=values.__getitem__,
        )

    @staticmethod
    def _trapezoidal_integral(
        values: tuple[float, ...],
        timestamps_ns: tuple[int, ...],
    ) -> float:
        total = 0.0

        for index in range(1, len(values)):
            dt_s = (
                timestamps_ns[index]
                - timestamps_ns[index - 1]
            ) / 1_000_000_000

            total += (
                0.5
                * (values[index - 1] + values[index])
                * dt_s
            )

        return total

    @staticmethod
    def _differentiate(
        values: tuple[float, ...],
        timestamps_ns: tuple[int, ...],
    ) -> tuple[float, ...]:
        derivatives: list[float] = []

        for index in range(1, len(values)):
            dt_s = (
                timestamps_ns[index]
                - timestamps_ns[index - 1]
            ) / 1_000_000_000

            derivatives.append(
                (values[index] - values[index - 1]) / dt_s
            )

        return tuple(derivatives)

    @staticmethod
    def _rms(values: tuple[float, ...]) -> float:
        if not values:
            return 0.0

        return math.sqrt(
            sum(value * value for value in values)
            / len(values)
        )
