from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Quaternion, Vector3
from .synchronizer import SynchronizedFrame


# Hardware calibration frame. Each transmitted quaternion is already relative
# to a two-second pose with the arm hanging straight down:
#   +X: down the arm toward the hand
#   +Y: horizontally outward
#   +Z: forward/backward
# Segment reconstruction therefore rotates +X; identity quaternions for both
# IMUs represent a straight, downward arm with an elbow angle of 180 degrees.
CALIBRATED_ARM_DOWN_AXIS = Vector3(1.0, 0.0, 0.0)
CALIBRATED_OUTWARD_AXIS = Vector3(0.0, 1.0, 0.0)
CALIBRATED_FORWARD_AXIS = Vector3(0.0, 0.0, 1.0)


class GeometryError(ValueError):
    """Raised when arm geometry cannot be calculated."""


@dataclass(frozen=True, slots=True)
class JointPositions:
    """Shoulder-relative joint positions measured in meters."""

    shoulder: Vector3
    elbow: Vector3
    wrist: Vector3

    def as_dict(self) -> dict[str, dict[str, float]]:
        return {
            "shoulder": self.shoulder.as_dict(),
            "elbow": self.elbow.as_dict(),
            "wrist": self.wrist.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ArmGeometry:
    """Geometry derived for one synchronized frame."""

    timestamp_ns: int
    upper_arm_direction: Vector3
    forearm_direction: Vector3
    joints: JointPositions
    elbow_angle_deg: float

    @property
    def timestamp_s(self) -> float:
        return self.timestamp_ns / 1_000_000_000

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp_s": self.timestamp_s,
            "upper_arm_direction": self.upper_arm_direction.as_dict(),
            "forearm_direction": self.forearm_direction.as_dict(),
            "joints_m": self.joints.as_dict(),
            "elbow_angle_deg": self.elbow_angle_deg,
        }


class ArmGeometryProcessor:
    """
    Reconstructs a shoulder-relative two-segment arm.

    Assumptions:
    - IMU 1 represents the forearm.
    - IMU 2 represents the upper arm.
    - Hardware quaternions are relative to the two-second arm-down pose.
    - Identity orientation uses +X down the arm, +Y outward, +Z forward.
    - Quaternions rotate calibrated sensor-local vectors into a shared frame.
    - Both local +X bone axes point from shoulder toward the hand.
    """

    def __init__(
        self,
        upper_arm_length_m: float,
        forearm_length_m: float,
        upper_arm_local_axis: Vector3 | None = None,
        forearm_local_axis: Vector3 | None = None,
    ) -> None:
        if upper_arm_length_m <= 0:
            raise ValueError(
                "upper_arm_length_m must be positive."
            )

        if forearm_length_m <= 0:
            raise ValueError(
                "forearm_length_m must be positive."
            )

        self.upper_arm_length_m = float(upper_arm_length_m)
        self.forearm_length_m = float(forearm_length_m)

        self.upper_arm_local_axis = self._normalize(
            upper_arm_local_axis or CALIBRATED_ARM_DOWN_AXIS
        )
        self.forearm_local_axis = self._normalize(
            forearm_local_axis or CALIBRATED_ARM_DOWN_AXIS
        )

    def process(
        self,
        frame: SynchronizedFrame,
    ) -> ArmGeometry:
        """Calculate geometry for one synchronized frame."""
        upper_arm_direction = self._rotate_vector(
            quaternion=frame.shoulder.quaternion_wxyz,
            vector=self.upper_arm_local_axis,
        )
        forearm_direction = self._rotate_vector(
            quaternion=frame.forearm.quaternion_wxyz,
            vector=self.forearm_local_axis,
        )

        upper_arm_direction = self._normalize(upper_arm_direction)
        forearm_direction = self._normalize(forearm_direction)

        joints = self._reconstruct_joints(
            upper_arm_direction=upper_arm_direction,
            forearm_direction=forearm_direction,
        )

        elbow_angle_deg = self._elbow_angle_deg(
            upper_arm_direction=upper_arm_direction,
            forearm_direction=forearm_direction,
        )

        return ArmGeometry(
            timestamp_ns=frame.timestamp_ns,
            upper_arm_direction=upper_arm_direction,
            forearm_direction=forearm_direction,
            joints=joints,
            elbow_angle_deg=elbow_angle_deg,
        )

    def process_all(
        self,
        frames: tuple[SynchronizedFrame, ...],
    ) -> tuple[ArmGeometry, ...]:
        """Calculate geometry for a complete synchronized swing."""
        if not frames:
            raise GeometryError(
                "At least one synchronized frame is required."
            )

        return tuple(self.process(frame) for frame in frames)

    def _reconstruct_joints(
        self,
        upper_arm_direction: Vector3,
        forearm_direction: Vector3,
    ) -> JointPositions:
        shoulder = Vector3(0.0, 0.0, 0.0)

        elbow = self._scale(
            upper_arm_direction,
            self.upper_arm_length_m,
        )

        wrist = self._add(
            elbow,
            self._scale(
                forearm_direction,
                self.forearm_length_m,
            ),
        )

        return JointPositions(
            shoulder=shoulder,
            elbow=elbow,
            wrist=wrist,
        )

    @staticmethod
    def _elbow_angle_deg(
        upper_arm_direction: Vector3,
        forearm_direction: Vector3,
    ) -> float:
        """
        Return the interior elbow angle.

        With both segment vectors pointing shoulder-to-hand:
        - straight arm is approximately 180 degrees;
        - a tightly folded human arm is approximately 35 degrees;
        - the mathematical calculation can range from 0 to 180 degrees.

        Values substantially below the expected anatomical minimum should be
        retained and later reported as possible sensor or geometry errors.
        """
        dot = (
            upper_arm_direction.x * forearm_direction.x
            + upper_arm_direction.y * forearm_direction.y
            + upper_arm_direction.z * forearm_direction.z
        )
        dot = max(-1.0, min(1.0, dot))

        direction_change_deg = math.degrees(math.acos(dot))
        return 180.0 - direction_change_deg

    @staticmethod
    def _rotate_vector(
        quaternion: Quaternion,
        vector: Vector3,
    ) -> Vector3:
        """
        Rotate a vector using q * v * conjugate(q).

        The quaternion is normalized before use.
        """
        q = ArmGeometryProcessor._normalize_quaternion(quaternion)

        # Optimized quaternion-vector rotation:
        # result = v + 2*w*(q_xyz × v) + 2*(q_xyz × (q_xyz × v))
        cross_x = q.y * vector.z - q.z * vector.y
        cross_y = q.z * vector.x - q.x * vector.z
        cross_z = q.x * vector.y - q.y * vector.x

        second_cross_x = q.y * cross_z - q.z * cross_y
        second_cross_y = q.z * cross_x - q.x * cross_z
        second_cross_z = q.x * cross_y - q.y * cross_x

        return Vector3(
            x=vector.x + 2.0 * (
                q.w * cross_x + second_cross_x
            ),
            y=vector.y + 2.0 * (
                q.w * cross_y + second_cross_y
            ),
            z=vector.z + 2.0 * (
                q.w * cross_z + second_cross_z
            ),
        )

    @staticmethod
    def _normalize(vector: Vector3) -> Vector3:
        magnitude = math.sqrt(
            vector.x * vector.x
            + vector.y * vector.y
            + vector.z * vector.z
        )

        if magnitude < 1e-12:
            raise GeometryError(
                "Cannot normalize a zero-length vector."
            )

        return Vector3(
            x=vector.x / magnitude,
            y=vector.y / magnitude,
            z=vector.z / magnitude,
        )

    @staticmethod
    def _normalize_quaternion(
        quaternion: Quaternion,
    ) -> Quaternion:
        norm = math.sqrt(
            quaternion.w * quaternion.w
            + quaternion.x * quaternion.x
            + quaternion.y * quaternion.y
            + quaternion.z * quaternion.z
        )

        if norm < 1e-12:
            raise GeometryError(
                "Cannot use a zero-length quaternion."
            )

        return Quaternion(
            w=quaternion.w / norm,
            x=quaternion.x / norm,
            y=quaternion.y / norm,
            z=quaternion.z / norm,
        )

    @staticmethod
    def _scale(vector: Vector3, scale: float) -> Vector3:
        return Vector3(
            x=vector.x * scale,
            y=vector.y * scale,
            z=vector.z * scale,
        )

    @staticmethod
    def _add(first: Vector3, second: Vector3) -> Vector3:
        return Vector3(
            x=first.x + second.x,
            y=first.y + second.y,
            z=first.z + second.z,
        )
