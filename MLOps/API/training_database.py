from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class TrainingDatabaseError(RuntimeError):
    """Raised when a collected swing cannot be persisted."""


class TrainingDatabase:
    """Stores raw swings and label-ready random-forest training records."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.raw_directory = self.root / "raw"
        self.training_directory = self.root / "training"
        self.failed_directory = self.root / "failed"
        for directory in (
            self.raw_directory,
            self.training_directory,
            self.failed_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def save_raw(self, swing_id: str, payload: dict[str, Any]) -> Path:
        return self._atomic_write(self.raw_directory, swing_id, payload)

    def save_training_record(
        self,
        swing_id: str,
        payload: dict[str, Any],
    ) -> Path:
        return self._atomic_write(self.training_directory, swing_id, payload)

    def save_failure(self, swing_id: str, payload: dict[str, Any]) -> Path:
        return self._atomic_write(self.failed_directory, swing_id, payload)

    @staticmethod
    def _atomic_write(
        directory: Path,
        swing_id: str,
        payload: dict[str, Any],
    ) -> Path:
        destination = directory / f"{swing_id}.json"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{swing_id}_",
                suffix=".tmp",
                dir=directory,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(payload, temporary, indent=2)
                temporary.write("\n")
            os.replace(temporary_path, destination)
        except (OSError, TypeError, ValueError) as exc:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
            raise TrainingDatabaseError(
                f"Unable to save training data to {destination}"
            ) from exc
        return destination
