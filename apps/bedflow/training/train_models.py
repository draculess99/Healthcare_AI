"""Offline training entry point for BedFlow AI Stage 5.

Run from the repository root:

    python training/train_models.py

This trains the three XGBoost models, publishes saved artifacts under models/,
updates database/model_metrics.json, appends database/model_metrics_history.json,
and regenerates models/model_card.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.data_sources import prepare_diabetes_readmission_data  # noqa: E402
from backend.models import bedflow_models  # noqa: E402


def main() -> int:
    print("Preparing Stage 6 public readmission dataset...")
    prepare_diabetes_readmission_data(force=False)
    metrics = bedflow_models.train_models(persist_artifacts=True)
    governance = bedflow_models.get_model_governance_summary()
    version = governance.get("active_model_version")
    print(f"BedFlow model training complete. Published version: {version}")
    print("Artifacts:")
    for name, item in governance.get("artifact_status", {}).items():
        print(f"  - {name}: {item.get('path')} exists={item.get('exists')} size_kb={item.get('size_kb')}")
    print("\nMetrics snapshot:")
    print(json.dumps({
        "discharge_delay": metrics.get("discharge_delay"),
        "readmission_risk": metrics.get("readmission_risk"),
        "expected_delay_hours": metrics.get("expected_delay_hours"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
