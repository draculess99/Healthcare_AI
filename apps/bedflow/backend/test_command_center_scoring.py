from __future__ import annotations

import pandas as pd

from backend.command_center import build_discharge_queue, build_hospital_capacity_snapshot
from backend.models import DATA_PATH, bedflow_models


def test_batch_model_scoring_drives_queue_without_target_columns():
    df = pd.read_csv(DATA_PATH, keep_default_na=False).head(12)
    predictions = bedflow_models.predict_dataframe(df)
    queue = build_discharge_queue(df, model_predictions=predictions)

    assert len(queue) == len(df)
    assert all(item["prediction_source"] in {"saved XGBoost artifacts", "in-memory XGBoost models"} for item in queue)
    assert all(0 <= item["discharge_delay_risk_probability"] <= 1 for item in queue)
    assert all(0 <= item["readmission_risk_probability"] <= 1 for item in queue)
    assert all(item["predicted_delay_hours"] >= 0 for item in queue)
    assert all(item["model_version"] for item in queue)

    # Changing known outcome labels must not change prospective model inference.
    modified = df.copy()
    modified["delayed_discharge"] = 1 - pd.to_numeric(modified["delayed_discharge"], errors="coerce").fillna(0)
    modified["readmitted_30_days"] = 1 - pd.to_numeric(modified["readmitted_30_days"], errors="coerce").fillna(0)
    modified["expected_discharge_delay_hours"] = 999
    rescored = bedflow_models.predict_dataframe(modified)

    pd.testing.assert_series_equal(
        predictions["discharge_delay_risk_probability"],
        rescored["discharge_delay_risk_probability"],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        predictions["readmission_risk_probability"],
        rescored["readmission_risk_probability"],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        predictions["predicted_delay_hours"],
        rescored["predicted_delay_hours"],
        check_names=False,
    )


def test_capacity_snapshot_is_explicitly_simulated_and_model_enriched():
    df = pd.read_csv(DATA_PATH, keep_default_na=False).head(30)
    predictions = bedflow_models.predict_dataframe(df)
    snapshot = build_hospital_capacity_snapshot(df, model_predictions=predictions)

    assert snapshot["is_simulated_capacity"] is True
    assert "model scoring" in snapshot["data_mode"].lower()
    assert snapshot["model_version"]
    assert snapshot["total_beds"] > 0
    assert snapshot["units"]
