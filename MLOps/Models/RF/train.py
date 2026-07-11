from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .artifact_store import RFArtifactStore
from .dataset import RFDatasetLoader
from .splitter import GroupAwareDatasetSplitter
from .trainer import RFTrainer


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Train the volleyball-sleeve random-forest classifier."
        )
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Directory containing labeled motion-profile JSON files.",
    )
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="Dataset filename pattern. Default: *.json",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        default=Path("MLOps/Models/RF/artifacts/rf_v1.joblib"),
        help="Destination .joblib model artifact.",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=None,
        help="Metrics JSON path. Defaults beside the artifact.",
    )
    parser.add_argument(
        "--model-version",
        default="1.0.0",
        help="Version stored inside the model artifact.",
    )
    parser.add_argument(
        "--validation-fraction",
        type=float,
        default=0.2,
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--min-samples-leaf",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
    )
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=-1,
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=25,
        help="Report validation progress after this many trees.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable incremental training output.",
    )
    return parser


def train_from_arguments(
    arguments: argparse.Namespace,
) -> dict[str, object]:
    dataset = RFDatasetLoader().load_directory(
        directory=arguments.dataset_dir,
        pattern=arguments.pattern,
    )
    splitter = GroupAwareDatasetSplitter(
        validation_fraction=arguments.validation_fraction,
        random_state=arguments.random_state,
    )
    trainer = RFTrainer(
        n_estimators=arguments.n_estimators,
        max_depth=arguments.max_depth,
        min_samples_leaf=arguments.min_samples_leaf,
        random_state=arguments.random_state,
        n_jobs=arguments.n_jobs,
        progress_interval=arguments.progress_interval,
        verbose=not arguments.quiet,
        splitter=splitter,
    )
    training_result = trainer.train(dataset)
    artifact_path = RFArtifactStore().save(
        training_result=training_result,
        path=arguments.artifact,
        model_version=arguments.model_version,
    )
    metrics_path = arguments.metrics or artifact_path.with_suffix(
        ".metrics.json"
    )
    summary = {
        "model_version": arguments.model_version,
        "artifact_path": str(artifact_path),
        "metrics_path": str(metrics_path),
        "dataset": {
            "directory": str(arguments.dataset_dir),
            "pattern": arguments.pattern,
            "sample_count": dataset.sample_count,
            "feature_count": dataset.feature_count,
            "class_counts": dataset.class_counts,
        },
        "training_configuration": {
            "validation_fraction": arguments.validation_fraction,
            "n_estimators": arguments.n_estimators,
            "max_depth": arguments.max_depth,
            "min_samples_leaf": arguments.min_samples_leaf,
            "random_state": arguments.random_state,
            "n_jobs": arguments.n_jobs,
            "progress_interval": arguments.progress_interval,
        },
        "training_result": training_result.summary_dict(),
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def print_summary(summary: dict[str, object]) -> None:
    dataset = summary["dataset"]
    result = summary["training_result"]
    metrics = result["metrics"]
    print("Random-forest training complete")
    print(f"Artifact: {summary['artifact_path']}")
    print(f"Metrics: {summary['metrics_path']}")
    print(
        f"Samples: {dataset['sample_count']} "
        f"({dataset['class_counts']})"
    )
    print(
        "Validation: "
        f"accuracy={metrics['accuracy']:.3f}, "
        f"precision_good={metrics['precision_good']:.3f}, "
        f"recall_good={metrics['recall_good']:.3f}, "
        f"f1_good={metrics['f1_good']:.3f}, "
        f"roc_auc={metrics['roc_auc']:.3f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)
    summary = train_from_arguments(arguments)
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
