from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ArmSide = Literal["L", "R"]

@dataclass(frozen=True, slots=True)
class Vector3:
    """A three-dimensional vector."""

    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z

    def as_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
        }
    
@dataclass(frozen=True, slots=True)
class Quaternion:
    """An orientation quaternion stored in wxyz order."""

    w: float
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.w, self.x, self.y, self.z

    def as_dict(self) -> dict[str, float]:
        return {
            "w": self.w,
            "x": self.x,
            "y": self.y,
            "z": self.z,
        }

@dataclass(frozen=True, slots=True)
class IMUSample:
    """One validated reading from one IMU."""

    timestamp_s: float
    accel_mps2: Vector3
    gyro_rads: Vector3
    quaternion_wxyz: Quaternion
    linear_accel_mps2: Vector3
    gravity_mps2: Vector3

    @property
    def timestamp_ns(self) -> int:
        """
        Return the Unix timestamp as integer nanoseconds.

        Internal synchronization should use this value instead of repeatedly
        subtracting large epoch-second floating-point values.
        """
        return round(self.timestamp_s * 1_000_000_000)

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp_s": self.timestamp_s,
            "accel_mps2": self.accel_mps2.as_dict(),
            "gyro_rads": self.gyro_rads.as_dict(),
            "quaternion_wxyz": self.quaternion_wxyz.as_dict(),
            "linear_accel_mps2": self.linear_accel_mps2.as_dict(),
            "gravity_mps2": self.gravity_mps2.as_dict(),
        }

@dataclass(frozen=True, slots=True)
class SwingData:
    """
    One complete validated arm recording.

    IMU 1 is always the forearm.
    IMU 2 is always the shoulder/upper-arm sensor.
    """

    side: ArmSide
    forearm_samples: tuple[IMUSample, ...]
    shoulder_samples: tuple[IMUSample, ...]

    @property
    def forearm_sample_count(self) -> int:
        return len(self.forearm_samples)

    @property
    def shoulder_sample_count(self) -> int:
        return len(self.shoulder_samples)

    @property
    def start_timestamp_s(self) -> float:
        return min(
            self.forearm_samples[0].timestamp_s,
            self.shoulder_samples[0].timestamp_s,
        )

    @property
    def end_timestamp_s(self) -> float:
        return max(
            self.forearm_samples[-1].timestamp_s,
            self.shoulder_samples[-1].timestamp_s,
        )

    @property
    def duration_s(self) -> float:
        return self.end_timestamp_s - self.start_timestamp_s