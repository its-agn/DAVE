from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from MLOps.Preprocessing.motion_profile import MotionProfile

from .artifact_store import (
    LoadedRFArtifact,
    RFArtifactStore,
)
from .feature_encoder import MotionProfileFeatureEncoder


class RFClassificationError(RuntimeError):
    """Raised when the random forest cannot classify a swing."""


@dataclass(frozen=True, slots=True)
class RFClassificationResult:
    """Binary random-forest classification output."""

    predicted_label: str
    predicted_class: int

    probability_good: float
    probability_bad: float
    score: int

    decision_threshold: float
    model_type: str
    model_version: str
    feature_schema_version: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class RFClassifier:
    """Runs random-forest inference on one motion profile."""

    def __init__(
        self,
        artifact: LoadedRFArtifact,
        decision_threshold: float = 0.5,
        encoder: MotionProfileFeatureEncoder | None = None,
    ) -> None:
        if not 0.0 <= decision_threshold <= 1.0:
            raise ValueError(
                "decision_threshold must be between 0 and 1."
            )

        self.artifact = artifact
        self.decision_threshold = decision_threshold
        self.encoder = encoder or MotionProfileFeatureEncoder()

        if (
            self.artifact.feature_names
            != self.encoder.FEATURE_NAMES
        ):
            raise RFClassificationError(
                "Model feature order does not match the encoder."
            )

        if (
            self.artifact.feature_schema_version
            != self.encoder.SCHEMA_VERSION
        ):
            raise RFClassificationError(
                "Model feature-schema version does not match "
                "the encoder."
            )

    @classmethod
    def from_artifact(
        cls,
        path: str | Path,
        decision_threshold: float = 0.5,
        artifact_store: RFArtifactStore | None = None,
    ) -> RFClassifier:
        store = artifact_store or RFArtifactStore()
        artifact = store.load(path)

        return cls(
            artifact=artifact,
            decision_threshold=decision_threshold,
        )

    def predict(
        self,
        profile: MotionProfile | Mapping[str, Any],
    ) -> RFClassificationResult:
        encoded = self.encoder.encode(profile)

        features = np.asarray(
            [encoded.values],
            dtype=np.float64,
        )

        probabilities = self.artifact.model.predict_proba(
            features
        )

        if probabilities.shape[0] != 1:
            raise RFClassificationError(
                "Expected one prediction row."
            )

        probability_good = self._class_probability(
            probabilities=probabilities,
            class_label=1,
        )
        probability_bad = self._class_probability(
            probabilities=probabilities,
            class_label=0,
        )

        predicted_good = (
            probability_good >= self.decision_threshold
        )

        predicted_class = 1 if predicted_good else 0
        predicted_label = "good" if predicted_good else "bad"

        return RFClassificationResult(
            predicted_label=predicted_label,
            predicted_class=predicted_class,
            probability_good=probability_good,
            probability_bad=probability_bad,
            score=round(probability_good * 100),
            decision_threshold=self.decision_threshold,
            model_type="random_forest",
            model_version=self.artifact.model_version,
            feature_schema_version=(
                self.artifact.feature_schema_version
            ),
        )

    def _class_probability(
        self,
        probabilities: np.ndarray,
        class_label: int,
    ) -> float:
        class_indices = np.where(
            self.artifact.model.classes_ == class_label
        )[0]

        if len(class_indices) != 1:
            raise RFClassificationError(
                f"Model does not contain class {class_label}."
            )

        probability = float(
            probabilities[0, int(class_indices[0])]
        )

        if not 0.0 <= probability <= 1.0:
            raise RFClassificationError(
                "Model returned an invalid probability."
            )

        return probability