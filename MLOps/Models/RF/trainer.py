from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from .dataset import RFDataset
from .feature_encoder import MotionProfileFeatureEncoder
from .splitter import DatasetSplit, GroupAwareDatasetSplitter


class RFTrainingError(RuntimeError):
    """Raised when the random forest cannot be trained or evaluated."""


@dataclass(frozen=True, slots=True)
class RFTrainingMetrics:
    """Validation metrics for one trained model."""

    accuracy: float
    precision_good: float
    recall_good: float
    f1_good: float
    roc_auc: float

    true_bad_predicted_bad: int
    true_bad_predicted_good: int
    true_good_predicted_bad: int
    true_good_predicted_good: int

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RFTrainingResult:
    """Trained model plus its validation information."""

    model: RandomForestClassifier
    metrics: RFTrainingMetrics

    feature_schema_version: str
    feature_names: tuple[str, ...]
    feature_importances: dict[str, float]

    training_sample_count: int
    validation_sample_count: int
    training_group_ids: tuple[str, ...]
    validation_group_ids: tuple[str, ...]

    def summary_dict(self) -> dict[str, object]:
        return {
            "metrics": self.metrics.as_dict(),
            "feature_schema_version": self.feature_schema_version,
            "feature_names": list(self.feature_names),
            "feature_importances": self.feature_importances,
            "training_sample_count": self.training_sample_count,
            "validation_sample_count": self.validation_sample_count,
            "training_group_ids": list(self.training_group_ids),
            "validation_group_ids": list(
                self.validation_group_ids
            ),
        }


class RFTrainer:
    """Trains and evaluates a binary good/bad random forest."""

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int | None = None,
        min_samples_leaf: int = 2,
        class_weight: str | dict[int, float] | None = "balanced",
        random_state: int = 42,
        n_jobs: int = -1,
        splitter: GroupAwareDatasetSplitter | None = None,
    ) -> None:
        if n_estimators <= 0:
            raise ValueError("n_estimators must be positive.")

        if max_depth is not None and max_depth <= 0:
            raise ValueError(
                "max_depth must be positive when provided."
            )

        if min_samples_leaf <= 0:
            raise ValueError(
                "min_samples_leaf must be positive."
            )

        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.class_weight = class_weight
        self.random_state = random_state
        self.n_jobs = n_jobs

        self.splitter = splitter or GroupAwareDatasetSplitter(
            random_state=random_state
        )

    def train(
        self,
        dataset: RFDataset,
    ) -> RFTrainingResult:
        self._validate_dataset_schema(dataset)

        split = self.splitter.split(dataset)

        model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            class_weight=self.class_weight,
            random_state=self.random_state,
            n_jobs=self.n_jobs,
        )

        model.fit(
            split.x_train,
            split.y_train,
        )

        metrics = self._evaluate(
            model=model,
            split=split,
        )

        importances = {
            feature_name: float(importance)
            for feature_name, importance in sorted(
                zip(
                    dataset.feature_names,
                    model.feature_importances_,
                ),
                key=lambda pair: pair[1],
                reverse=True,
            )
        }

        return RFTrainingResult(
            model=model,
            metrics=metrics,
            feature_schema_version=(
                MotionProfileFeatureEncoder.SCHEMA_VERSION
            ),
            feature_names=dataset.feature_names,
            feature_importances=importances,
            training_sample_count=split.x_train.shape[0],
            validation_sample_count=(
                split.x_validation.shape[0]
            ),
            training_group_ids=split.train_group_ids,
            validation_group_ids=split.validation_group_ids,
        )

    @staticmethod
    def _evaluate(
        model: RandomForestClassifier,
        split: DatasetSplit,
    ) -> RFTrainingMetrics:
        predictions = model.predict(split.x_validation)

        probability_good = RFTrainer._good_probabilities(
            model,
            split.x_validation,
        )

        matrix = confusion_matrix(
            split.y_validation,
            predictions,
            labels=[0, 1],
        )

        if matrix.shape != (2, 2):
            raise RFTrainingError(
                "Expected a 2x2 binary confusion matrix."
            )

        return RFTrainingMetrics(
            accuracy=float(
                accuracy_score(
                    split.y_validation,
                    predictions,
                )
            ),
            precision_good=float(
                precision_score(
                    split.y_validation,
                    predictions,
                    pos_label=1,
                    zero_division=0,
                )
            ),
            recall_good=float(
                recall_score(
                    split.y_validation,
                    predictions,
                    pos_label=1,
                    zero_division=0,
                )
            ),
            f1_good=float(
                f1_score(
                    split.y_validation,
                    predictions,
                    pos_label=1,
                    zero_division=0,
                )
            ),
            roc_auc=float(
                roc_auc_score(
                    split.y_validation,
                    probability_good,
                )
            ),
            true_bad_predicted_bad=int(matrix[0, 0]),
            true_bad_predicted_good=int(matrix[0, 1]),
            true_good_predicted_bad=int(matrix[1, 0]),
            true_good_predicted_good=int(matrix[1, 1]),
        )

    @staticmethod
    def _good_probabilities(
        model: RandomForestClassifier,
        features: np.ndarray,
    ) -> np.ndarray:
        probabilities = model.predict_proba(features)

        class_indices = np.where(model.classes_ == 1)[0]

        if len(class_indices) != 1:
            raise RFTrainingError(
                "The trained model does not contain class 1."
            )

        return probabilities[:, int(class_indices[0])]

    @staticmethod
    def _validate_dataset_schema(
        dataset: RFDataset,
    ) -> None:
        expected = MotionProfileFeatureEncoder.FEATURE_NAMES

        if dataset.feature_names != expected:
            raise RFTrainingError(
                "Dataset feature schema does not match the "
                "MotionProfileFeatureEncoder schema."
            )

        if dataset.sample_count < 4:
            raise RFTrainingError(
                "At least four samples are required for training."
            )

        if set(np.unique(dataset.labels)) != {0, 1}:
            raise RFTrainingError(
                "Training requires both good and bad labels."
            )