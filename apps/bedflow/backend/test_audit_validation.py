from __future__ import annotations

from backend.audit import log_human_decision
from backend.auth import DEFAULT_DEMO_PASSWORD


def test_audit_record_contains_authenticated_reviewer_and_model_version(tmp_path, monkeypatch):
    audit_path = tmp_path / "audit.json"
    monkeypatch.setattr("backend.audit.AUDIT_LOG_PATH", str(audit_path))

    record = log_human_decision(
        patient_id="P-TEST",
        model_outputs={"delay_risk_level": "Low", "readmission_risk_level": "Low"},
        research_outputs={},
        committee_rec="Recommend clinician review",
        human_decision="Approve",
        human_note="Checklist verified.",
        memory_insight="No similar case.",
        reviewer_name="Alex Morgan",
        reviewer_role="Bed Manager",
        reviewer_user_id="USR-TEST",
        authentication_source="local-demo-rbac",
        model_version="model-test-1",
    )

    assert record["audit_id"].startswith("AUD-")
    assert record["reviewer_name"] == "Alex Morgan"
    assert record["reviewer_role"] == "Bed Manager"
    assert record["reviewer_user_id"] == "USR-TEST"
    assert record["authentication_source"] == "local-demo-rbac"
    assert record["model_version"] == "model-test-1"
    assert record["timestamp_utc"].endswith("+00:00")


def _login(client, username="bedmanager"):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": DEFAULT_DEMO_PASSWORD},
    )
    assert response.status_code == 200
    token = response.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_api_requires_authentication_and_exception_rationale():
    from backend.api import app

    client = app.test_client()
    base = {
        "patient_id": "P-TEST",
        "human_decision": "Override",
        "model_outputs": {},
        "research_outputs": {},
    }

    missing_auth = client.post("/api/save_human_decision", json=base)
    assert missing_auth.status_code == 401

    headers = _login(client)
    missing_reason = client.post("/api/save_human_decision", json=base, headers=headers)
    assert missing_reason.status_code == 400


def test_role_cannot_record_unpermitted_decision():
    from backend.api import app

    client = app.test_client()
    nurse_headers = _login(client, "nurse")
    response = client.post(
        "/api/save_human_decision",
        json={
            "patient_id": "P-TEST",
            "human_decision": "Approve",
            "model_outputs": {},
            "research_outputs": {},
        },
        headers=nurse_headers,
    )
    assert response.status_code == 403
