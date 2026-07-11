"""Non-destructive smoke checks for the packaged BedFlow AI application."""

from __future__ import annotations

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from backend.api import app
from backend.auth import DEFAULT_DEMO_PASSWORD
from backend.committee import run_committee
from backend.memory import get_memory_state, init_memory
from backend.models import DATA_PATH, bedflow_models


def test_imports() -> None:
    print("Imports successful.")


def test_dataset() -> None:
    assert os.path.exists(DATA_PATH), "Dataset not found"
    print("Dataset check passed.")


def test_models() -> None:
    assert bedflow_models.is_trained, "Saved model artifacts were not loaded"
    patient = pd.read_csv(DATA_PATH, keep_default_na=False).iloc[0].to_dict()
    outputs = bedflow_models.predict_patient(patient)
    assert 0 <= outputs["discharge_delay_risk_probability"] <= 1
    assert 0 <= outputs["readmission_risk_probability"] <= 1
    assert outputs["predicted_delay_hours"] >= 0
    print("Saved model inference check passed.")


def test_api() -> None:
    client = app.test_client()
    for path in (
        "/api/health",
        "/api/ready",
        "/api/system/version",
        "/api/hospital_capacity",
        "/api/discharge_queue?limit=3",
        "/api/fhir/capability",
        "/api/simulations/capability",
        "/api/auth/demo_users",
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
    queue = client.get("/api/discharge_queue?limit=3").get_json()
    assert queue and all(item.get("model_version") for item in queue)

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": DEFAULT_DEMO_PASSWORD},
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.get("/api/audit_log", headers=headers).status_code == 200
    assert client.get("/api/tasks/events", headers=headers).status_code == 200
    metrics = client.get("/api/metrics", headers=headers)
    assert metrics.status_code == 200
    assert metrics.get_json().get("total_requests", 0) > 0
    health = client.get("/api/health", headers={"X-Request-ID": "SMOKE-REQUEST-ID"})
    assert health.headers.get("X-Request-ID") == "SMOKE-REQUEST-ID"
    assert health.headers.get("X-Response-Time-Ms") is not None
    simulation = client.post(
        "/api/simulations/run",
        json={
            "scenario": {
                "scenario_name": "Smoke-test scenario",
                "scope_unit": "Med/Surg",
                "pharmacy_clearance_percent": 10,
                "horizon_hours": 24,
            },
            "save": False,
        },
        headers=headers,
    )
    assert simulation.status_code == 200
    assert simulation.get_json().get("simulation_method")
    print("API, Stage 8 authentication, Stage 9 simulation, Stage 10A observability, and model-scored queue checks passed.")


def test_committee() -> None:
    sample_patient = {
        "patient_id": "TEST001",
        "diagnosis_group": "Cardiology",
        "acuity_level": "Medium",
        "mobility_status": "Independent",
        "home_support_level": "Good",
        "discharge_destination": "Home",
        "lab_stability_flag": "Stable",
        "vital_sign_stability_flag": "Stable",
        "ed_wait_time_pressure": "Medium",
        "medication_complexity": "Low",
        "primary_discharge_bottleneck": "Pharmacy",
    }
    predictions = bedflow_models.predict_patient(sample_patient)
    result = run_committee(sample_patient, predictions)
    assert "final_recommendation" in result
    print("Committee logic check passed.")


def test_memory() -> None:
    init_memory()
    state = get_memory_state()
    assert "recent_avg_discharge_delay_hours" in state
    print("Memory read check passed.")


if __name__ == "__main__":
    print("Starting smoke tests...")
    test_imports()
    test_dataset()
    test_models()
    test_api()
    test_committee()
    test_memory()
    print("All smoke tests passed!")
