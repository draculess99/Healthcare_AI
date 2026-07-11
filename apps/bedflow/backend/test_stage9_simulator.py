from __future__ import annotations

import json

import pandas as pd

from backend.auth import DEFAULT_DEMO_PASSWORD
from backend.command_center import build_hospital_capacity_snapshot
from backend.simulator import (
    list_simulation_runs,
    normalize_scenario,
    run_capacity_simulation,
    save_simulation_run,
    simulation_runs_csv,
)


def _risk(probability: float) -> str:
    if probability < 0.2:
        return "Low"
    if probability < 0.5:
        return "Medium"
    if probability < 0.8:
        return "High"
    return "Critical"


def _fake_scorer(frame: pd.DataFrame) -> pd.DataFrame:
    records = []
    blocker_fields = [
        "pharmacy_med_rec_pending",
        "insurance_authorization_pending",
        "transport_pending",
        "rehab_snf_placement_pending",
        "home_care_setup_pending",
        "social_work_pending",
        "family_pickup_pending",
    ]
    for _, row in frame.iterrows():
        blocker_count = sum(int(float(row.get(field, 0) or 0)) for field in blocker_fields)
        delay_probability = min(0.95, 0.1 + blocker_count * 0.25)
        delay_hours = 1.0 + blocker_count * 6.0
        records.append(
            {
                "patient_id": str(row.get("patient_id")),
                "discharge_delay_risk_probability": delay_probability,
                "delay_risk_level": _risk(delay_probability),
                "readmission_risk_probability": 0.25,
                "readmission_risk_level": "Medium",
                "predicted_delay_hours": delay_hours,
                "model_version": "test-model-v1",
                "prediction_source": "test scorer",
                "prediction_timestamp_utc": "2026-07-11T00:00:00+00:00",
            }
        )
    return pd.DataFrame(records)


def _patients() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "patient_id": "P-READY",
                "diagnosis_group": "General Medicine",
                "acuity_level": "Medium",
                "lab_stability_flag": "Stable",
                "vital_sign_stability_flag": "Stable",
                "doctor_signoff_pending": 0,
                "pharmacy_med_rec_pending": 1,
                "insurance_authorization_pending": 0,
                "transport_pending": 0,
                "rehab_snf_placement_pending": 0,
                "home_care_setup_pending": 0,
                "social_work_pending": 0,
                "family_pickup_pending": 0,
                "case_manager_available": 1,
                "primary_discharge_bottleneck": "Pharmacy",
                "current_bed_occupancy_percent": 90,
                "ed_boarding_count": 8,
            },
            {
                "patient_id": "P-UNSTABLE",
                "diagnosis_group": "Cardiology",
                "acuity_level": "High",
                "lab_stability_flag": "Unstable",
                "vital_sign_stability_flag": "Stable",
                "doctor_signoff_pending": 1,
                "pharmacy_med_rec_pending": 1,
                "insurance_authorization_pending": 0,
                "transport_pending": 0,
                "rehab_snf_placement_pending": 0,
                "home_care_setup_pending": 0,
                "social_work_pending": 0,
                "family_pickup_pending": 0,
                "case_manager_available": 1,
                "primary_discharge_bottleneck": "Clinical Stability",
                "current_bed_occupancy_percent": 95,
                "ed_boarding_count": 10,
            },
        ]
    )


def test_scenario_normalization_clamps_and_validates():
    scenario = normalize_scenario(
        {
            "scope_unit": "All Units",
            "horizon_hours": 500,
            "pharmacy_clearance_percent": 150,
            "temporary_beds_opened": -4,
        }
    )
    assert scenario["horizon_hours"] == 72
    assert scenario["pharmacy_clearance_percent"] == 100
    assert scenario["temporary_beds_opened"] == 0


def test_simulation_re_scores_operational_changes_without_clearing_clinical_fields():
    patients = _patients()
    current_predictions = _fake_scorer(patients)
    current_capacity = build_hospital_capacity_snapshot(patients, current_predictions)
    captured = {}

    def capturing_scorer(frame: pd.DataFrame) -> pd.DataFrame:
        captured["simulated"] = frame.copy()
        return _fake_scorer(frame)

    result = run_capacity_simulation(
        patient_df=patients,
        current_predictions=current_predictions,
        scoring_fn=capturing_scorer,
        scenario_payload={
            "scenario_name": "Clear pharmacy",
            "scope_unit": "All Units",
            "horizon_hours": 24,
            "pharmacy_clearance_percent": 100,
        },
        current_capacity=current_capacity,
        actor={"display_name": "Jordan Lee", "role": "Bed Manager"},
    )

    assert result["summary"]["operational_blockers_removed"] == 2
    assert result["summary"]["additional_review_candidates"] == 1
    assert result["summary"]["delay_hours_removed"] > 0
    simulated = captured["simulated"].set_index("patient_id")
    assert simulated.loc["P-UNSTABLE", "lab_stability_flag"] == "Unstable"
    assert int(simulated.loc["P-UNSTABLE", "doctor_signoff_pending"]) == 1
    assert result["safety"]["clinical_fields_modified"] is False


def test_saved_simulation_history_and_csv(tmp_path):
    path = tmp_path / "simulation_runs.json"
    result = {
        "simulation_id": "SIM-TEST",
        "created_at_utc": "2026-07-11T00:00:00+00:00",
        "scenario": {"scenario_name": "Test", "scope_unit": "All Units"},
        "actor": {"display_name": "Jordan Lee", "role": "Bed Manager"},
        "model_version": "v1",
        "summary": {
            "patients_changed": 2,
            "patients_improved": 1,
            "additional_review_candidates": 1,
            "potential_beds_recovered_from_workflow": 1,
            "additional_potential_capacity": 2,
            "delay_hours_removed": 8.5,
            "potential_ed_boarder_reduction": 2,
            "operational_blockers_removed": 2,
        },
    }
    saved = save_simulation_run(result, path=str(path))
    assert saved["saved"] is True
    runs = list_simulation_runs(path=str(path))
    assert len(runs) == 1
    assert runs[0]["simulation_id"] == "SIM-TEST"
    csv_text = simulation_runs_csv(runs)
    assert "SIM-TEST" in csv_text
    assert "delay_hours_removed" in csv_text


def test_stage9_api_requires_bedflow_capacity_role():
    from backend.api import app

    client = app.test_client()
    nurse_login = client.post(
        "/api/auth/login",
        json={"username": "nurse", "password": DEFAULT_DEMO_PASSWORD},
    ).get_json()
    denied = client.post(
        "/api/simulations/run",
        json={"scenario": {"scenario_name": "Not permitted"}},
        headers={"Authorization": f"Bearer {nurse_login['token']}"},
    )
    assert denied.status_code == 403
    task_sync_denied = client.post(
        "/api/tasks/sync",
        json={"patient_data": {"patient_id": "P-NO-SYNC"}, "discharge_checklist": {"blockers": []}},
        headers={"Authorization": f"Bearer {nurse_login['token']}"},
    )
    assert task_sync_denied.status_code == 403

    manager_login = client.post(
        "/api/auth/login",
        json={"username": "bedmanager", "password": DEFAULT_DEMO_PASSWORD},
    ).get_json()
    allowed = client.post(
        "/api/simulations/run",
        json={
            "scenario": {
                "scenario_name": "API smoke scenario",
                "scope_unit": "Med/Surg",
                "pharmacy_clearance_percent": 10,
                "horizon_hours": 24,
            },
            "save": False,
        },
        headers={"Authorization": f"Bearer {manager_login['token']}"},
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload["status"] == "success"
    assert payload["actor"]["role"] == "Bed Manager"
    assert payload["saved"] is False
