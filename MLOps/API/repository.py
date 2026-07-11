from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class SwingRepositoryError(RuntimeError):
    """Raised when swing data cannot be persisted."""


class SwingRepository:
    """Stores raw, processed, and failed swing records as JSON."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)
        for category in ("raw", "processed", "failed"):
            (self.data_root / category).mkdir(parents=True, exist_ok=True)

    def save_raw(self, swing_id: str, payload: dict[str, Any]) -> Path:
        return self._save("raw", swing_id, payload)

    def save_processed(self, swing_id: str, payload: dict[str, Any]) -> Path:
        return self._save("processed", swing_id, payload)

    def save_failure(self, swing_id: str, payload: dict[str, Any]) -> Path:
        return self._save("failed", swing_id, payload)

    def load_processed(self, swing_id: str) -> dict[str, Any] | None:
        path = self.data_root / "processed" / f"{swing_id}.json"
        if not path.is_file():
            return None
        try:
            with path.open(encoding="utf-8") as file:
                value = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise SwingRepositoryError(f"Unable to load {path}") from exc
        if not isinstance(value, dict):
            raise SwingRepositoryError(f"Processed record is not an object: {path}")
        return value

    def _save(
        self,
        category: str,
        swing_id: str,
        payload: dict[str, Any],
    ) -> Path:
        directory = self.data_root / category
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
            raise SwingRepositoryError(f"Unable to save {destination}") from exc
        return destination
