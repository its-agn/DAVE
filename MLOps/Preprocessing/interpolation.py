from __future__ import annotations

import math

from .models import IMUSample, Quaternion, Vector3


class InterpolationError(ValueError):
    """Raised when two IMU samples cannot be interpolated."""


class IMUSampleInterpolator:
    """Interpolates between timestamped IMU samples."""

    def interpolate(
        self,
        first: IMUSample,
        second: IMUSample,
        target_timestamp_ns: int,
    ) -> IMUSample:
        """
        Interpolate one IMU reading at the requested timestamp.

        Vector fields use linear interpolation.
        Orientation uses quaternion spherical interpolation (SLERP).
        """
        first_ns = first.timestamp_ns
        second_ns = second.timestamp_ns

        if second_ns <= first_ns:
            raise InterpolationError(
                "The second sample must occur after the first sample."
            )

        if target_timestamp_ns < first_ns:
            raise InterpolationError(
                "Target timestamp occurs before the interpolation interval."
            )

        if target_timestamp_ns > second_ns:
            raise InterpolationError(
                "Target timestamp occurs after the interpolation interval."
            )

        if target_timestamp_ns == first_ns:
            return first

        if target_timestamp_ns == second_ns:
            return second

        fraction = (
            (target_timestamp_ns - first_ns)
            / (second_ns - first_ns)
        )

        return IMUSample(
            timestamp_s=target_timestamp_ns / 1_000_000_000,
            accel_mps2=self._lerp_vector(
                first.accel_mps2,
                second.accel_mps2,
                fraction,
            ),
            gyro_rads=self._lerp_vector(
                first.gyro_rads,
                second.gyro_rads,
                fraction,
            ),
            quaternion_wxyz=self._slerp_quaternion(
                first.quaternion_wxyz,
                second.quaternion_wxyz,
                fraction,
            ),
            linear_accel_mps2=self._lerp_vector(
                first.linear_accel_mps2,
                second.linear_accel_mps2,
                fraction,
            ),
            gravity_mps2=self._lerp_vector(
                first.gravity_mps2,
                second.gravity_mps2,
                fraction,
            ),
        )

    @staticmethod
    def _lerp_vector(
        first: Vector3,
        second: Vector3,
        fraction: float,
    ) -> Vector3:
        return Vector3(
            x=first.x + fraction * (second.x - first.x),
            y=first.y + fraction * (second.y - first.y),
            z=first.z + fraction * (second.z - first.z),
        )

    @staticmethod
    def _slerp_quaternion(
        first: Quaternion,
        second: Quaternion,
        fraction: float,
    ) -> Quaternion:
        """
        Interpolate orientation along the shortest rotational path.

        Quaternions q and -q represent the same orientation. If their dot
        product is negative, the second quaternion is flipped so interpolation
        does not take the long path around the orientation sphere.
        """
        q1 = IMUSampleInterpolator._normalize_quaternion(first)
        q2 = IMUSampleInterpolator._normalize_quaternion(second)

        dot = (
            q1.w * q2.w
            + q1.x * q2.x
            + q1.y * q2.y
            + q1.z * q2.z
        )

        if dot < 0.0:
            q2 = Quaternion(
                w=-q2.w,
                x=-q2.x,
                y=-q2.y,
                z=-q2.z,
            )
            dot = -dot

        dot = max(-1.0, min(1.0, dot))

        # Nearly identical quaternions are more stable with normalized
        # linear interpolation.
        if dot > 0.9995:
            result = Quaternion(
                w=q1.w + fraction * (q2.w - q1.w),
                x=q1.x + fraction * (q2.x - q1.x),
                y=q1.y + fraction * (q2.y - q1.y),
                z=q1.z + fraction * (q2.z - q1.z),
            )
            return IMUSampleInterpolator._normalize_quaternion(result)

        angle = math.acos(dot)
        sin_angle = math.sin(angle)

        first_weight = math.sin((1.0 - fraction) * angle) / sin_angle
        second_weight = math.sin(fraction * angle) / sin_angle

        result = Quaternion(
            w=first_weight * q1.w + second_weight * q2.w,
            x=first_weight * q1.x + second_weight * q2.x,
            y=first_weight * q1.y + second_weight * q2.y,
            z=first_weight * q1.z + second_weight * q2.z,
        )

        return IMUSampleInterpolator._normalize_quaternion(result)

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
            raise InterpolationError(
                "Cannot normalize a zero-length quaternion."
            )

        return Quaternion(
            w=quaternion.w / norm,
            x=quaternion.x / norm,
            y=quaternion.y / norm,
            z=quaternion.z / norm,
        )