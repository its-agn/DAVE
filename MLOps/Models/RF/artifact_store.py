from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import sklearn
from sklearn.ensemble import RandomForestClassifier

from .feature_encoder import MotionProfileFeatureEncoder
from .trainer import RFTrainingResult


class RFArtifactError(RuntimeError):
    """Raised when an RF model artifact cannot be saved or loaded."""


@dataclass(frozen=True, slots=True)
class LoadedRFArtifact:
    """Validated random-forest model and its metadata."""

    model: RandomForestClassifier
    model_version: str
    feature_schema_version: str
    feature_names: tuple[str, ...]
    trained_at_utc: str
    training_summary: dict[str, Any]


class RFArtifactStore:
    """Saves and loads versioned random-forest artifacts."""

    ARTIFACT_FORMAT_VERSION = "1.0.0"

    def save(
        self,
        training_result: RFTrainingResult,
        path: str | Path,
        model_version: str,
    ) -> Path:
        if not model_version.strip():
            raise RFArtifactError(
                "model_version must be a nonempty string."
            )

        artifact_path = Path(path)

        if artifact_path.suffix != ".joblib":
            raise RFArtifactError(
                "Random-forest artifacts must use '.joblib'."
            )

        artifact_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        trained_at = datetime.now(
            timezone.utc
        ).isoformat()

        bundle = {
            "artifact_format_version": (
                self.ARTIFACT_FORMAT_VERSION
            ),
            "model_type": "random_forest_binary",
            "model_version": model_version,
            "trained_at_utc": trained_at,

            "feature_schema_version": (
                training_result.feature_schema_version
            ),
            "feature_names": list(
                training_result.feature_names
            ),

            "class_labels": {
                "bad": 0,
                "good": 1,
            },

            "library_versions": {
                "scikit_learn": sklearn.__version__,
                "joblib": joblib.__version__,
            },

            "training_summary": (
                training_result.summary_dict()
            ),

            "model": training_result.model,
        }

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{artifact_path.stem}_",
                suffix=".tmp",
                dir=artifact_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)

            joblib.dump(
                bundle,
                temporary_path,
                compress=3,
            )

            os.replace(
                temporary_path,
                artifact_path,
            )
        except Exception as exc:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()

            raise RFArtifactError(
                f"Unable to save model artifact: {artifact_path}"
            ) from exc

        return artifact_path

    def load(
        self,
        path: str | Path,
    ) -> LoadedRFArtifact:
        artifact_path = Path(path)

        if not artifact_path.is_file():
            raise RFArtifactError(
                f"Model artifact does not exist: {artifact_path}"
            )

        try:
            bundle = joblib.load(artifact_path)
        except Exception as exc:
            raise RFArtifactError(
                f"Unable to load model artifact: {artifact_path}"
            ) from exc

        if not isinstance(bundle, dict):
            raise RFArtifactError(
                "Model artifact must contain a dictionary."
            )

        self._require_equal(
            bundle,
            key="artifact_format_version",
            expected=self.ARTIFACT_FORMAT_VERSION,
        )
        self._require_equal(
            bundle,
            key="model_type",
            expected="random_forest_binary",
        )
        self._require_equal(
            bundle,
            key="feature_schema_version",
            expected=MotionProfileFeatureEncoder.SCHEMA_VERSION,
        )

        feature_names = bundle.get("feature_names")

        if not isinstance(feature_names, list):
            raise RFArtifactError(
                "Artifact feature_names must be a list."
            )

        feature_names_tuple = tuple(feature_names)

        if (
            feature_names_tuple
            != MotionProfileFeatureEncoder.FEATURE_NAMES
        ):
            raise RFArtifactError(
                "Artifact feature order does not match the "
                "current feature encoder."
            )

        model = bundle.get("model")

        if not isinstance(model, RandomForestClassifier):
            raise RFArtifactError(
                "Artifact does not contain a RandomForestClassifier."
            )

        if not hasattr(model, "classes_"):
            raise RFArtifactError(
                "Artifact contains an unfitted model."
            )

        if set(model.classes_) != {0, 1}:
            raise RFArtifactError(
                "Artifact model must contain classes 0 and 1."
            )

        model_version = bundle.get("model_version")
        trained_at = bundle.get("trained_at_utc")
        training_summary = bundle.get("training_summary")

        if not isinstance(model_version, str):
            raise RFArtifactError(
                "Artifact model_version must be a string."
            )

        if not isinstance(trained_at, str):
            raise RFArtifactError(
                "Artifact trained_at_utc must be a string."
            )

        if not isinstance(training_summary, dict):
            raise RFArtifactError(
                "Artifact training_summary must be a dictionary."
            )

        return LoadedRFArtifact(
            model=model,
            model_version=model_version,
            feature_schema_version=bundle[
                "feature_schema_version"
            ],
            feature_names=feature_names_tuple,
            trained_at_utc=trained_at,
            training_summary=training_summary,
        )

    @staticmethod
    def _require_equal(
        bundle: dict[str, Any],
        key: str,
        expected: Any,
    ) -> None:
        value = bundle.get(key)

        if value != expected:
            raise RFArtifactError(
                f"Artifact '{key}' is {value!r}; "
                f"expected {expected!r}."
            )