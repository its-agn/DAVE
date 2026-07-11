from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .frame_features import FrameFeatureExtractor
from .geometry import ArmGeometryProcessor
from .models import Vector3
from .motion_profile import MotionProfileBuilder
from .result import PreprocessingResult
from .synchronizer import IMUSynchronizer
from .temporal_features import TemporalFeatureBuilder
from .validator import IMUPayloadValidator


class PreprocessingPipeline:
    """
    Runs the complete preprocessing flow for one arm recording.

    This class does not:
    - parse raw HTTP bytes;
    - run a classifier;
    - produce a score;
    - format the final frontend response.
    """

    def __init__(
        self,
        target_sample_rate_hz: float | None = None,
        maximum_interpolation_gap_s: float = 0.02,
        quaternion_norm_tolerance: float = 0.05,
        near_full_extension_deg: float = 165.0,
        expected_minimum_elbow_angle_deg: float = 10.0,
        upper_arm_local_axis: Vector3 | None = None,
        forearm_local_axis: Vector3 | None = None,
    ) -> None:
        self.validator = IMUPayloadValidator(
            quaternion_norm_tolerance=(
                quaternion_norm_tolerance
            )
        )

        self.synchronizer = IMUSynchronizer(
            target_sample_rate_hz=target_sample_rate_hz,
            maximum_interpolation_gap_s=(
                maximum_interpolation_gap_s
            ),
        )

        self.frame_feature_extractor = FrameFeatureExtractor()

        self.motion_profile_builder = MotionProfileBuilder(
            near_full_extension_deg=near_full_extension_deg,
            expected_minimum_elbow_angle_deg=(
                expected_minimum_elbow_angle_deg
            ),
        )

        self.temporal_feature_builder = TemporalFeatureBuilder()

        self.upper_arm_local_axis = (
            upper_arm_local_axis
            or Vector3(1.0, 0.0, 0.0)
        )
        self.forearm_local_axis = (
            forearm_local_axis
            or Vector3(1.0, 0.0, 0.0)
        )

    def process(
        self,
        payload: Mapping[str, Any],
        upper_arm_length_m: float,
        forearm_length_m: float,
    ) -> PreprocessingResult:
        """
        Preprocess one parsed IMU payload.

        Args:
            payload:
                Parsed JSON with side, IMU 1, and IMU 2.
            upper_arm_length_m:
                Shoulder-to-elbow length in meters.
            forearm_length_m:
                Elbow-to-wrist length in meters.

        Returns:
            Replay frames, random-forest profile, and CNN features.
        """
        validated_swing = self.validator.validate(payload)

        synchronized_frames = self.synchronizer.synchronize(
            validated_swing
        )

        geometry_processor = ArmGeometryProcessor(
            upper_arm_length_m=upper_arm_length_m,
            forearm_length_m=forearm_length_m,
            upper_arm_local_axis=self.upper_arm_local_axis,
            forearm_local_axis=self.forearm_local_axis,
        )

        geometries = geometry_processor.process_all(
            synchronized_frames
        )

        frame_features = self.frame_feature_extractor.extract(
            frames=synchronized_frames,
            geometries=geometries,
        )

        motion_profile = self.motion_profile_builder.build(
            frame_features
        )

        temporal_features = self.temporal_feature_builder.build(
            synchronized_frames=synchronized_frames,
            frame_features=frame_features,
        )

        return PreprocessingResult(
            side=validated_swing.side,
            upper_arm_length_m=upper_arm_length_m,
            forearm_length_m=forearm_length_m,
            frames=frame_features,
            motion_profile=motion_profile,
            temporal_features=temporal_features,
        )
