#!/usr/bin/env bash

set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/_common.sh"

echo "Checking RF imports, training, persistence, and inference..."

"$PYTHON" -m compileall -q "$MLOPS_ROOT/Models/RF"

"$PYTHON" - <<'PY'
from pathlib import Path

import numpy as np

from MLOps.Models.RF import (
    MotionProfileFeatureEncoder,
    RFArtifactStore,
    RFClassifier,
    RFDataset,
    RFTrainer,
)

names = MotionProfileFeatureEncoder.FEATURE_NAMES
rows = []
labels = []
swing_ids = []
group_ids = []

for label in (0, 1):
    for group in range(4):
        for variation in range(2):
            value = float(label * 10 + group * 0.1 + variation * 0.01)
            rows.append([value] * len(names))
            labels.append(label)
            swing_ids.append(f"{label}-{group}-{variation}")
            group_ids.append(f"{label}-{group}")

dataset = RFDataset(
    features=np.asarray(rows, dtype=np.float64),
    labels=np.asarray(labels, dtype=np.int64),
    swing_ids=tuple(swing_ids),
    group_ids=tuple(group_ids),
    feature_names=names,
)

training = RFTrainer(
    n_estimators=10,
    progress_interval=5,
    random_state=42,
).train(dataset)

artifact_path = Path("/tmp/dave_rf_smoke_test.joblib")
RFArtifactStore().save(
    training_result=training,
    path=artifact_path,
    model_version="smoke-test",
)

classifier = RFClassifier.from_artifact(artifact_path)
profile = dict(zip(names, rows[-1]))
prediction = classifier.predict(profile)

if prediction.predicted_label != "good":
    raise SystemExit(f"Unexpected smoke-test prediction: {prediction}")

print(
    f"PASS RF: accuracy={training.metrics.accuracy:.3f}, "
    f"prediction={prediction.predicted_label}, "
    f"score={prediction.score}"
)
PY

echo "RF checks passed."
