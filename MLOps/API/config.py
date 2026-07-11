from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class APIConfig:
    """Runtime settings for the local DAVE API."""

    data_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[1] / "data"
    )
    upper_arm_length_m: float = 0.26035
    forearm_length_m: float = 0.26035
    maximum_request_bytes: int = 4 * 1024 * 1024
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    )

    @classmethod
    def from_environment(cls) -> APIConfig:
        defaults = cls()
        origins = os.getenv("DAVE_CORS_ORIGINS")
        return cls(
            data_root=Path(
                os.getenv("DAVE_DATA_ROOT", str(defaults.data_root))
            ),
            upper_arm_length_m=float(
                os.getenv("DAVE_UPPER_ARM_LENGTH_M", "0.26035")
            ),
            forearm_length_m=float(
                os.getenv("DAVE_FOREARM_LENGTH_M", "0.26035")
            ),
            maximum_request_bytes=int(
                os.getenv("DAVE_MAX_REQUEST_BYTES", str(4 * 1024 * 1024))
            ),
            cors_origins=(
                tuple(item.strip() for item in origins.split(",") if item.strip())
                if origins
                else defaults.cors_origins
            ),
        )
