from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter

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
from sklearn.utils.class_weight import compute_class_weight

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
    """
    Trains and evaluates a binary good/bad random forest.

    Random forests do not have epochs. Training progress is reported
    after each configured batch of newly added trees.
    """

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int | None = None,
        min_samples_leaf: int = 2,
        class_weight: str | dict[int, float] | None = "balanced",
        random_state: int = 42,
        n_jobs: int = -1,
        progress_interval: int = 25,
        verbose: bool = True,
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

        if progress_interval <= 0:
            raise ValueError(
                "progress_interval must be positive."
            )

        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.class_weight = class_weight
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.progress_interval = progress_interval
        self.verbose = verbose

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
            n_estimators=min(
                self.progress_interval,
                self.n_estimators,
            ),
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            class_weight=self._resolve_class_weight(split.y_train),
            random_state=self.random_state,
            n_jobs=self.n_jobs,
            warm_start=True,
        )

        self._fit_with_progress(
            model=model,
            split=split,
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

    def _resolve_class_weight(
        self,
        labels: np.ndarray,
    ) -> str | dict[int, float] | None:
        if self.class_weight != "balanced":
            return self.class_weight

        classes = np.unique(labels)
        weights = compute_class_weight(
            class_weight="balanced",
            classes=classes,
            y=labels,
        )
        return {
            int(class_label): float(weight)
            for class_label, weight in zip(classes, weights)
        }

    def _fit_with_progress(
        self,
        model: RandomForestClassifier,
        split: DatasetSplit,
    ) -> None:
        started_at = perf_counter()

        if self.verbose:
            print("Starting random-forest training", flush=True)
            print(
                f"Training samples: {len(split.y_train)}",
                flush=True,
            )
            print(
                f"Validation samples: {len(split.y_validation)}",
                flush=True,
            )
            print(
                f"Features: {split.x_train.shape[1]}",
                flush=True,
            )
            print(
                f"Target trees: {self.n_estimators}",
                flush=True,
            )
            print(
                f"Progress interval: {self.progress_interval} trees",
                flush=True,
            )

        tree_count = min(
            self.progress_interval,
            self.n_estimators,
        )

        while True:
            model.set_params(n_estimators=tree_count)
            batch_started_at = perf_counter()
            model.fit(split.x_train, split.y_train)
            batch_duration = perf_counter() - batch_started_at
            total_duration = perf_counter() - started_at

            if self.verbose:
                self._print_progress(
                    model=model,
                    split=split,
                    tree_count=tree_count,
                    batch_duration_s=batch_duration,
                    total_duration_s=total_duration,
                )

            if tree_count >= self.n_estimators:
                break

            tree_count = min(
                tree_count + self.progress_interval,
                self.n_estimators,
            )

        if self.verbose:
            print(
                f"Training finished in "
                f"{perf_counter() - started_at:.2f}s",
                flush=True,
            )

    @staticmethod
    def _print_progress(
        model: RandomForestClassifier,
        split: DatasetSplit,
        tree_count: int,
        batch_duration_s: float,
        total_duration_s: float,
    ) -> None:
        predictions = model.predict(split.x_validation)
        probability_good = RFTrainer._good_probabilities(
            model,
            split.x_validation,
        )

        accuracy = accuracy_score(
            split.y_validation,
            predictions,
        )
        f1 = f1_score(
            split.y_validation,
            predictions,
            pos_label=1,
            zero_division=0,
        )
        roc_auc = roc_auc_score(
            split.y_validation,
            probability_good,
        )

        print(
            f"Trees {tree_count:4d} | "
            f"accuracy={accuracy:.3f} | "
            f"f1_good={f1:.3f} | "
            f"roc_auc={roc_auc:.3f} | "
            f"batch={batch_duration_s:.2f}s | "
            f"total={total_duration_s:.2f}s",
            flush=True,
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
