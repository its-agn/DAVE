#!/usr/bin/env bash

set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/_common.sh"

echo "Checking preprocessing modules and fixtures..."

"$PYTHON" -m compileall -q "$MLOPS_ROOT/Preprocessing"

"$PYTHON" - <<'PY'
import json
from pathlib import Path

from MLOps.Preprocessing import PreprocessingPipeline
from MLOps.Preprocessing.geometry import ArmGeometryProcessor
from MLOps.Preprocessing.models import Quaternion, Vector3

identity = Quaternion(w=1.0, x=0.0, y=0.0, z=0.0)
down = Vector3(1.0, 0.0, 0.0)
rotated_down = ArmGeometryProcessor._rotate_vector(identity, down)
if rotated_down != down:
    raise AssertionError("Identity calibration must preserve the +X down axis.")
if ArmGeometryProcessor._elbow_angle_deg(down, down) != 180.0:
    raise AssertionError("Arm-down calibration pose must produce 180 degrees.")

fixtures = Path("MLOps/Preprocessing/tests/fixtures")
paths = sorted(fixtures.glob("JSONtest_*.json"))
if not paths:
    raise SystemExit(f"No preprocessing fixtures found in {fixtures}")

pipeline = PreprocessingPipeline()
for path in paths:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    result = pipeline.process(
        payload=payload,
        upper_arm_length_m=0.25654,
        forearm_length_m=0.26670,
    )
    print(
        f"PASS {path.name}: side={result.side}, "
        f"frames={result.frame_count}, "
        f"features={result.temporal_features.feature_count}"
    )
PY

echo "Preprocessing checks passed."
