from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from MLOps.Preprocessing.motion_profile import MotionProfile


class FeatureEncodingError(ValueError):
    """Raised when a motion profile cannot become an RF feature row."""


@dataclass(frozen=True, slots=True)
class EncodedFeatures:
    """One fixed-order random-forest feature row."""

    feature_names: tuple[str, ...]
    values: tuple[float, ...]

    def as_dict(self) -> dict[str, float]:
        return dict(zip(self.feature_names, self.values))


class MotionProfileFeatureEncoder:
    """
    Converts a MotionProfile into the exact numeric feature order expected
    by the random forest.

    Training and inference must use this same class.
    """

    SCHEMA_VERSION = "1.0.0"

    FEATURE_NAMES = (
        "duration_s",
        "frame_count",

        "elbow_angle_min_deg",
        "elbow_angle_max_deg",
        "elbow_range_of_motion_deg",

        "peak_elbow_extension_velocity_dps",
        "peak_elbow_flexion_velocity_dps",
        "peak_elbow_angular_acceleration_dps2",

        "peak_forearm_gyro_rads",
        "peak_upper_arm_gyro_rads",

        "peak_forearm_linear_accel_mps2",
        "peak_upper_arm_linear_accel_mps2",
        "peak_wrist_speed_mps",

        "forearm_gyro_peak_time_s",
        "upper_arm_gyro_peak_time_s",
        "gyro_peak_timing_difference_ms",

        "forearm_accel_impulse_mps",
        "upper_arm_accel_impulse_mps",

        "elbow_acceleration_rms_dps2",
        "elbow_jerk_rms_dps3",

        "reached_near_full_extension",
        "elbow_angle_below_expected_range",
    )

    def encode(
        self,
        profile: MotionProfile | Mapping[str, Any],
    ) -> EncodedFeatures:
        """
        Encode one motion profile.

        Accepts either the MotionProfile object produced directly by
        preprocessing or its serialized dictionary representation.
        """
        if isinstance(profile, MotionProfile):
            source = profile.as_dict()
        elif isinstance(profile, Mapping):
            source = profile
        else:
            raise FeatureEncodingError(
                "profile must be MotionProfile or a mapping."
            )

        values = tuple(
            self._numeric_value(
                value=source.get(feature_name),
                feature_name=feature_name,
            )
            for feature_name in self.FEATURE_NAMES
        )

        return EncodedFeatures(
            feature_names=self.FEATURE_NAMES,
            values=values,
        )

    def encode_many(
        self,
        profiles: list[MotionProfile | Mapping[str, Any]],
    ) -> tuple[EncodedFeatures, ...]:
        if not profiles:
            raise FeatureEncodingError(
                "At least one motion profile is required."
            )

        return tuple(
            self.encode(profile)
            for profile in profiles
        )

    @staticmethod
    def _numeric_value(
        value: Any,
        feature_name: str,
    ) -> float:
        if value is None:
            raise FeatureEncodingError(
                f"Missing required feature '{feature_name}'."
            )

        if isinstance(value, bool):
            return 1.0 if value else 0.0

        if not isinstance(value, (int, float)):
            raise FeatureEncodingError(
                f"Feature '{feature_name}' must be numeric."
            )

        number = float(value)

        if not math.isfinite(number):
            raise FeatureEncodingError(
                f"Feature '{feature_name}' must be finite."
            )

        return number