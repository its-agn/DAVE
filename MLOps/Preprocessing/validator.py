from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .models import IMUSample, Quaternion, SwingData, Vector3


class IMUValidationError(ValueError):
    """Raised when an IMU payload violates the expected contract."""


class IMUPayloadValidator:
    """
    Validates one complete arm recording.

    Fixed sensor mapping:
        IMU 1 = forearm
        IMU 2 = shoulder/upper arm
    """

    SIDE_KEY = "side"
    FOREARM_KEY = "IMU 1"
    SHOULDER_KEY = "IMU 2"

    VECTOR_FIELDS = (
        "accel_mps2",
        "gyro_rads",
        "linear_accel_mps2",
        "gravity_mps2",
    )

    QUATERNION_FIELD = "quaternion_wxyz"
    TIMESTAMP_FIELD = "timestamp_s"

    def __init__(
        self,
        quaternion_norm_tolerance: float = 0.05,
    ) -> None:
        if quaternion_norm_tolerance < 0:
            raise ValueError(
                "quaternion_norm_tolerance cannot be negative."
            )

        self.quaternion_norm_tolerance = quaternion_norm_tolerance

    def validate(
        self,
        payload: Mapping[str, Any],
    ) -> SwingData:
        """
        Validate a parsed HTTP or file payload.

        Returns:
            A typed, immutable SwingData object.

        Raises:
            IMUValidationError:
                If any required field is missing or invalid.
        """
        if not isinstance(payload, Mapping):
            raise IMUValidationError(
                "The IMU payload must be a JSON object."
            )

        side = self._validate_side(payload.get(self.SIDE_KEY))

        forearm_raw = self._require_sample_array(
            payload,
            key=self.FOREARM_KEY,
        )
        shoulder_raw = self._require_sample_array(
            payload,
            key=self.SHOULDER_KEY,
        )

        forearm_samples = self._validate_samples(
            forearm_raw,
            imu_name=self.FOREARM_KEY,
        )
        shoulder_samples = self._validate_samples(
            shoulder_raw,
            imu_name=self.SHOULDER_KEY,
        )

        return SwingData(
            side=side,
            forearm_samples=forearm_samples,
            shoulder_samples=shoulder_samples,
        )

    @staticmethod
    def _validate_side(value: Any) -> str:
        if value not in ("L", "R"):
            raise IMUValidationError(
                "'side' must be either 'L' or 'R'."
            )

        return value

    @staticmethod
    def _require_sample_array(
        payload: Mapping[str, Any],
        key: str,
    ) -> Sequence[Any]:
        if key not in payload:
            raise IMUValidationError(
                f"Missing required top-level field '{key}'."
            )

        samples = payload[key]

        if (
            not isinstance(samples, Sequence)
            or isinstance(samples, (str, bytes, bytearray))
        ):
            raise IMUValidationError(
                f"'{key}' must be an array."
            )

        if not samples:
            raise IMUValidationError(
                f"'{key}' must contain at least one sample."
            )

        return samples

    def _validate_samples(
        self,
        samples: Sequence[Any],
        imu_name: str,
    ) -> tuple[IMUSample, ...]:
        validated: list[IMUSample] = []
        previous_timestamp: float | None = None

        for index, raw_sample in enumerate(samples):
            path = f"{imu_name}[{index}]"

            if not isinstance(raw_sample, Mapping):
                raise IMUValidationError(
                    f"{path} must be a JSON object."
                )

            sample = self._validate_sample(
                raw_sample,
                path=path,
            )

            if (
                previous_timestamp is not None
                and sample.timestamp_s <= previous_timestamp
            ):
                raise IMUValidationError(
                    f"{path}.timestamp_s must be greater than "
                    f"the previous timestamp."
                )

            validated.append(sample)
            previous_timestamp = sample.timestamp_s

        return tuple(validated)

    def _validate_sample(
        self,
        sample: Mapping[str, Any],
        path: str,
    ) -> IMUSample:
        timestamp = self._require_number(
            sample,
            key=self.TIMESTAMP_FIELD,
            path=path,
        )

        if timestamp <= 0:
            raise IMUValidationError(
                f"{path}.timestamp_s must be a positive Unix timestamp."
            )

        vectors = {
            field: self._validate_vector(
                sample,
                key=field,
                path=path,
            )
            for field in self.VECTOR_FIELDS
        }

        quaternion = self._validate_quaternion(
            sample,
            path=path,
        )

        return IMUSample(
            timestamp_s=timestamp,
            accel_mps2=vectors["accel_mps2"],
            gyro_rads=vectors["gyro_rads"],
            quaternion_wxyz=quaternion,
            linear_accel_mps2=vectors["linear_accel_mps2"],
            gravity_mps2=vectors["gravity_mps2"],
        )

    def _validate_vector(
        self,
        sample: Mapping[str, Any],
        key: str,
        path: str,
    ) -> Vector3:
        value = self._require_mapping(
            sample,
            key=key,
            path=path,
        )

        return Vector3(
            x=self._require_number(value, "x", f"{path}.{key}"),
            y=self._require_number(value, "y", f"{path}.{key}"),
            z=self._require_number(value, "z", f"{path}.{key}"),
        )

    def _validate_quaternion(
        self,
        sample: Mapping[str, Any],
        path: str,
    ) -> Quaternion:
        key = self.QUATERNION_FIELD

        value = self._require_mapping(
            sample,
            key=key,
            path=path,
        )

        quaternion = Quaternion(
            w=self._require_number(value, "w", f"{path}.{key}"),
            x=self._require_number(value, "x", f"{path}.{key}"),
            y=self._require_number(value, "y", f"{path}.{key}"),
            z=self._require_number(value, "z", f"{path}.{key}"),
        )

        norm = math.sqrt(
            quaternion.w * quaternion.w
            + quaternion.x * quaternion.x
            + quaternion.y * quaternion.y
            + quaternion.z * quaternion.z
        )

        if abs(norm - 1.0) > self.quaternion_norm_tolerance:
            raise IMUValidationError(
                f"{path}.{key} must be normalized; "
                f"received norm {norm:.6f}."
            )

        return quaternion

    @staticmethod
    def _require_mapping(
        source: Mapping[str, Any],
        key: str,
        path: str,
    ) -> Mapping[str, Any]:
        if key not in source:
            raise IMUValidationError(
                f"Missing required field '{path}.{key}'."
            )

        value = source[key]

        if not isinstance(value, Mapping):
            raise IMUValidationError(
                f"'{path}.{key}' must be a JSON object."
            )

        return value

    @staticmethod
    def _require_number(
        source: Mapping[str, Any],
        key: str,
        path: str,
    ) -> float:
        if key not in source:
            raise IMUValidationError(
                f"Missing required field '{path}.{key}'."
            )

        value = source[key]

        # bool is a subclass of int in Python and must be rejected explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise IMUValidationError(
                f"'{path}.{key}' must be a number."
            )

        number = float(value)

        if not math.isfinite(number):
            raise IMUValidationError(
                f"'{path}.{key}' must be finite."
            )

        return number