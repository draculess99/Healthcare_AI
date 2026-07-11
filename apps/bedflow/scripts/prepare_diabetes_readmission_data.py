"""Prepare the public readmission training layer for BedFlow AI Stage 6.

Run from the repository root:

    python scripts/prepare_diabetes_readmission_data.py

This transforms dataset_diabetes/diabetic_data.csv into
database/readmission_training_data.csv using the BedFlow feature schema.

The transformed dataset is used for the 30-day readmission-risk model. The
discharge-delay and expected-delay-hours models continue to use the synthetic
BedFlow operational dataset.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.data_sources import prepare_diabetes_readmission_data, get_data_sources_summary  # noqa: E402


def main() -> int:
    summary = prepare_diabetes_readmission_data(force=True)
    print("Stage 6 public readmission dataset prepared.")
    print(json.dumps(summary, indent=2))
    print("\nData-source summary:")
    print(json.dumps(get_data_sources_summary(ensure_readmission=False), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
