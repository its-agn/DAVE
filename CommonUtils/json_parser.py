from __future__ import annotations

import json
from pathlib import Path
from typing import Any

class IMUJsonError(ValueError):
    """Raised when an error occurs while parsing a JSON file."""

class IMUJsonParser:
    """
    Parses volleyball-sleeve IMU JSON.

    Expected session format:

    {
        "session": {...},
        "samples": [...]
    }

    This class only parses the JSON and validates its top-level structure.
    Detailed sample validation belongs in a separate validation module.
    """

    @classmethod
    def from_string(cls, json_text: str) -> dict[str, Any]:
        """ Parse a complete session from a JSON string. Raises IMUJsonError if the JSON is invalid or does not have the expected structure. """
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise IMUJsonError(
                f"Invalid JSON at line {exc.lineno}, "
                f"column {exc.colno}: {exc.msg}"
            ) from exc

        if not isinstance(data, dict):
            raise IMUJsonError("Expected top-level JSON object to be a dictionary.")

        if "session" not in data or "samples" not in data:
            raise IMUJsonError("JSON must contain 'session' and 'samples' keys.")

        return cls._validate_top_level(data)
    
    @classmethod
    def from_file(cls, file_path: Path) -> dict[str, Any]:
        """ Parse a complete session from a JSON file. Raises IMUJsonError if the JSON is invalid or does not have the expected structure. """
        if not file_path.is_file():
            raise IMUJsonError(f"File not found: {file_path}")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json_text = f.read()
        except OSError as exc:
            raise IMUJsonError(f"Failed to read file {file_path}: {exc}") from exc

        return cls.from_string(json_text)
    
    @staticmethod
    def _validate_top_level(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise IMUJsonError(
                "The top-level JSON value must be an object."
            )

        for imu_name in ("IMU 1", "IMU 2"):
            if imu_name not in data:
                raise IMUJsonError(
                    f"The request must contain '{imu_name}'."
                )

            if not isinstance(data[imu_name], list):
                raise IMUJsonError(
                    f"'{imu_name}' must be an array."
                )

            if not data[imu_name]:
                raise IMUJsonError(
                    f"'{imu_name}' cannot be empty."
                )

        session = data.get("session", {})

        if not isinstance(session, dict):
            raise IMUJsonError(
                "'session' must be an object when provided."
            )

        return data
    
    @classmethod
    def from_http_body(cls, body: bytes | str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(body, dict):
            return cls._validate_top_level(body)

        if isinstance(body, bytes):
            try:
                body = body.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise IMUJsonError(
                    "HTTP request body must use UTF-8 encoding."
                ) from exc

        if isinstance(body, str):
            return cls.from_string(body)

        raise IMUJsonError(
            "HTTP request body must be bytes, a JSON string, or a dictionary."
        )