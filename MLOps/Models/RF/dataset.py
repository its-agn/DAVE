from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .feature_encoder import MotionProfileFeatureEncoder


class RFDatasetError(ValueError):
    """Raised when an RF training dataset is invalid."""


@dataclass(frozen=True, slots=True)
class RFDataset:
    """Numeric dataset ready for scikit-learn."""

    features: np.ndarray
    labels: np.ndarray
    swing_ids: tuple[str, ...]
    group_ids: tuple[str, ...]
    feature_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.features.ndim != 2:
            raise RFDatasetError(
                "features must be a two-dimensional matrix."
            )

        if self.labels.ndim != 1:
            raise RFDatasetError(
                "labels must be a one-dimensional array."
            )

        row_count = self.features.shape[0]

        if row_count == 0:
            raise RFDatasetError(
                "The dataset must contain at least one swing."
            )

        if self.labels.shape[0] != row_count:
            raise RFDatasetError(
                "Feature and label counts do not match."
            )

        if len(self.swing_ids) != row_count:
            raise RFDatasetError(
                "Feature and swing-ID counts do not match."
            )

        if len(self.group_ids) != row_count:
            raise RFDatasetError(
                "Feature and group-ID counts do not match."
            )

        if self.features.shape[1] != len(self.feature_names):
            raise RFDatasetError(
                "Feature columns do not match the feature schema."
            )

        if not np.isfinite(self.features).all():
            raise RFDatasetError(
                "The feature matrix contains non-finite values."
            )

        if not set(np.unique(self.labels)).issubset({0, 1}):
            raise RFDatasetError(
                "Labels must contain only 0 and 1."
            )

    @property
    def sample_count(self) -> int:
        return self.features.shape[0]

    @property
    def feature_count(self) -> int:
        return self.features.shape[1]

    @property
    def class_counts(self) -> dict[str, int]:
        return {
            "bad": int(np.sum(self.labels == 0)),
            "good": int(np.sum(self.labels == 1)),
        }


class RFDatasetLoader:
    """
    Loads labeled motion profiles from JSON files or in-memory records.

    Supported labels:
        good -> 1
        bad  -> 0
    """

    LABELS = {
        "bad": 0,
        "good": 1,
    }

    def __init__(
        self,
        encoder: MotionProfileFeatureEncoder | None = None,
    ) -> None:
        self.encoder = encoder or MotionProfileFeatureEncoder()

    def load_directory(
        self,
        directory: str | Path,
        pattern: str = "*.json",
    ) -> RFDataset:
        directory_path = Path(directory)

        if not directory_path.is_dir():
            raise RFDatasetError(
                f"Dataset directory does not exist: {directory_path}"
            )

        paths = tuple(sorted(directory_path.glob(pattern)))

        if not paths:
            raise RFDatasetError(
                f"No files matching '{pattern}' in {directory_path}"
            )

        return self.load_files(paths)

    def load_files(
        self,
        paths: Sequence[str | Path],
    ) -> RFDataset:
        if not paths:
            raise RFDatasetError(
                "At least one dataset file is required."
            )

        records: list[Mapping[str, Any]] = []

        for path in paths:
            file_path = Path(path)

            try:
                with file_path.open("r", encoding="utf-8") as file:
                    record = json.load(file)
            except FileNotFoundError as exc:
                raise RFDatasetError(
                    f"Dataset file does not exist: {file_path}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise RFDatasetError(
                    f"Invalid JSON in {file_path} at line "
                    f"{exc.lineno}, column {exc.colno}: {exc.msg}"
                ) from exc
            except OSError as exc:
                raise RFDatasetError(
                    f"Unable to read dataset file: {file_path}"
                ) from exc

            if not isinstance(record, Mapping):
                raise RFDatasetError(
                    f"Top-level JSON in {file_path} must be an object."
                )

            records.append(record)

        return self.load_records(records)

    def load_records(
        self,
        records: Sequence[Mapping[str, Any]],
    ) -> RFDataset:
        if not records:
            raise RFDatasetError(
                "At least one training record is required."
            )

        feature_rows: list[tuple[float, ...]] = []
        labels: list[int] = []
        swing_ids: list[str] = []
        group_ids: list[str] = []

        seen_swing_ids: set[str] = set()

        for index, record in enumerate(records):
            path = f"record[{index}]"

            swing_id = self._required_string(
                record,
                key="swing_id",
                path=path,
            )

            if swing_id in seen_swing_ids:
                raise RFDatasetError(
                    f"Duplicate swing_id '{swing_id}'."
                )

            seen_swing_ids.add(swing_id)

            group_id = record.get("group_id", swing_id)

            if not isinstance(group_id, str) or not group_id.strip():
                raise RFDatasetError(
                    f"{path}.group_id must be a nonempty string."
                )

            label_text = self._required_string(
                record,
                key="label",
                path=path,
            ).lower()

            if label_text not in self.LABELS:
                raise RFDatasetError(
                    f"{path}.label must be 'good' or 'bad'."
                )

            motion_profile = self._find_motion_profile(
                record,
                path=path,
            )
            encoded = self.encoder.encode(motion_profile)

            feature_rows.append(encoded.values)
            labels.append(self.LABELS[label_text])
            swing_ids.append(swing_id)
            group_ids.append(group_id)

        return RFDataset(
            features=np.asarray(
                feature_rows,
                dtype=np.float64,
            ),
            labels=np.asarray(
                labels,
                dtype=np.int64,
            ),
            swing_ids=tuple(swing_ids),
            group_ids=tuple(group_ids),
            feature_names=self.encoder.FEATURE_NAMES,
        )

    @staticmethod
    def _find_motion_profile(
        record: Mapping[str, Any],
        path: str,
    ) -> Mapping[str, Any]:
        # Compact training-record format.
        direct = record.get("motion_profile")

        if isinstance(direct, Mapping):
            return direct

        # Complete serialized preprocessing-result format.
        preprocessing = record.get("preprocessing")

        if isinstance(preprocessing, Mapping):
            nested = preprocessing.get("motion_profile")

            if isinstance(nested, Mapping):
                return nested

        raise RFDatasetError(
            f"{path} must contain 'motion_profile' or "
            "'preprocessing.motion_profile'."
        )

    @staticmethod
    def _required_string(
        source: Mapping[str, Any],
        key: str,
        path: str,
    ) -> str:
        value = source.get(key)

        if not isinstance(value, str) or not value.strip():
            raise RFDatasetError(
                f"{path}.{key} must be a nonempty string."
            )

        return value.strip()