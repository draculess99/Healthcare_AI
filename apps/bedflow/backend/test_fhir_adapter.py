from backend.fhir_adapter import build_fhir_bundle, summarize_bundle


def test_build_fhir_bundle_has_expected_resources():
    patient = {"patient_id": "BF-001", "unit": "3 West", "length_of_stay_days": 4, "diagnosis_group": "Cardiac"}
    outputs = {"discharge_delay_risk_probability": 0.72, "readmission_risk_probability": 0.31, "predicted_delay_hours": 18}
    checklist = {"readiness_status": "Blocked", "completion_percent": 65, "items": [{"status": "Blocked", "recommended_action": "Complete medication reconciliation", "owner_role": "Pharmacy"}]}
    tasks = [{"task_id": "T-1", "status": "Pending", "title": "Medication reconciliation", "owner_role": "Pharmacy"}]
    bundle = build_fhir_bundle(patient, outputs, checklist, tasks)
    summary = summarize_bundle(bundle)
    assert bundle["resourceType"] == "Bundle"
    assert summary["resource_types"]["Patient"] == 1
    assert summary["resource_types"]["Encounter"] == 1
    assert summary["resource_types"]["Task"] == 1
    assert summary["resource_types"]["CarePlan"] == 1
    assert summary["resource_types"]["Observation"] >= 3
