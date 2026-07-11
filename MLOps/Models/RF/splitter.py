from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from .dataset import RFDataset


class DatasetSplitError(ValueError):
    """Raised when a valid train/validation split cannot be created."""


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    """Indices and arrays for one train/validation split."""

    train_indices: np.ndarray
    validation_indices: np.ndarray

    x_train: np.ndarray
    y_train: np.ndarray

    x_validation: np.ndarray
    y_validation: np.ndarray

    train_group_ids: tuple[str, ...]
    validation_group_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.x_train.shape[0] != self.y_train.shape[0]:
            raise DatasetSplitError(
                "Training feature and label counts do not match."
            )

        if (
            self.x_validation.shape[0]
            != self.y_validation.shape[0]
        ):
            raise DatasetSplitError(
                "Validation feature and label counts do not match."
            )

        overlap = set(self.train_group_ids).intersection(
            self.validation_group_ids
        )

        if overlap:
            raise DatasetSplitError(
                f"Groups appear in both splits: {sorted(overlap)}"
            )


class GroupAwareDatasetSplitter:
    """
    Splits complete groups instead of randomly mixing related swings.

    It retries several deterministic seeds until both training and
    validation contain good and bad examples.
    """

    def __init__(
        self,
        validation_fraction: float = 0.2,
        random_state: int = 42,
        maximum_attempts: int = 100,
    ) -> None:
        if not 0.0 < validation_fraction < 1.0:
            raise ValueError(
                "validation_fraction must be between 0 and 1."
            )

        if maximum_attempts <= 0:
            raise ValueError(
                "maximum_attempts must be positive."
            )

        self.validation_fraction = validation_fraction
        self.random_state = random_state
        self.maximum_attempts = maximum_attempts

    def split(
        self,
        dataset: RFDataset,
    ) -> DatasetSplit:
        unique_groups = set(dataset.group_ids)

        if len(unique_groups) < 2:
            raise DatasetSplitError(
                "At least two distinct groups are required."
            )

        if set(np.unique(dataset.labels)) != {0, 1}:
            raise DatasetSplitError(
                "The complete dataset must contain both good and bad labels."
            )

        groups = np.asarray(dataset.group_ids)

        for attempt in range(self.maximum_attempts):
            splitter = GroupShuffleSplit(
                n_splits=1,
                test_size=self.validation_fraction,
                random_state=self.random_state + attempt,
            )

            train_indices, validation_indices = next(
                splitter.split(
                    dataset.features,
                    dataset.labels,
                    groups=groups,
                )
            )

            y_train = dataset.labels[train_indices]
            y_validation = dataset.labels[validation_indices]

            if set(np.unique(y_train)) != {0, 1}:
                continue

            if set(np.unique(y_validation)) != {0, 1}:
                continue

            train_groups = tuple(
                sorted(set(groups[train_indices]))
            )
            validation_groups = tuple(
                sorted(set(groups[validation_indices]))
            )

            return DatasetSplit(
                train_indices=train_indices,
                validation_indices=validation_indices,
                x_train=dataset.features[train_indices],
                y_train=y_train,
                x_validation=dataset.features[
                    validation_indices
                ],
                y_validation=y_validation,
                train_group_ids=train_groups,
                validation_group_ids=validation_groups,
            )

        raise DatasetSplitError(
            "Unable to create a group-separated split containing "
            "both classes in training and validation. Add more groups "
            "for each label or adjust validation_fraction."
        )