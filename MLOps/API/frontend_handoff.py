from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from MLOps.Postprocessing import PostprocessingBundle


class FrontendHandoffError(RuntimeError):
    """Raised when completed output cannot be handed to the website."""


class FrontendHandoff:
    """Atomically publishes completed swing files for the website."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)
        self.swings_directory = self.data_root / "swings"
        self.gemini_directory = self.data_root / "gemini"
        self.swings_directory.mkdir(parents=True, exist_ok=True)
        self.gemini_directory.mkdir(parents=True, exist_ok=True)

    def publish(self, bundle: PostprocessingBundle) -> dict[str, Any]:
        swing_id = bundle.frontend.get("swing_id")
        if not isinstance(swing_id, str) or not swing_id:
            raise FrontendHandoffError("Frontend payload has no swing_id.")

        swing_relative = Path("swings") / f"{swing_id}.json"
        gemini_relative = Path("gemini") / f"{swing_id}.json"
        self._atomic_write(self.data_root / swing_relative, bundle.frontend)
        self._atomic_write(self.data_root / gemini_relative, bundle.gemini)

        latest = {
            "status": "complete",
            "swing_id": swing_id,
            "side": bundle.frontend.get("side"),
            "completed_at": bundle.frontend.get("processed_at"),
            "swing_file": swing_relative.as_posix(),
            "gemini_file": gemini_relative.as_posix(),
        }
        # Publish the pointer last so readers never observe incomplete files.
        self._atomic_write(self.data_root / "latest.json", latest)
        return latest

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{path.stem}_",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(payload, temporary, indent=2)
                temporary.write("\n")
            os.replace(temporary_path, path)
        except (OSError, TypeError, ValueError) as exc:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
            raise FrontendHandoffError(f"Unable to publish {path}") from exc
