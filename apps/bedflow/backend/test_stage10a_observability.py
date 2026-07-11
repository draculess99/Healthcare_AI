from __future__ import annotations

import zipfile

from backend.auth import DEFAULT_DEMO_PASSWORD
from backend.observability import APP_VERSION, reset_metrics_for_tests
from scripts.check_secrets import scan
from scripts.package_release import build_zip


def _admin_headers(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": DEFAULT_DEMO_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def test_health_exposes_version_request_id_timing_and_security_headers():
    from backend.api import app

    reset_metrics_for_tests()
    client = app.test_client()
    response = client.get("/api/health", headers={"X-Request-ID": "REQ-TEST-123"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["app_version"] == APP_VERSION
    assert payload["upgrade_stage"] == "10A"
    assert response.headers["X-Request-ID"] == "REQ-TEST-123"
    assert float(response.headers["X-Response-Time-Ms"]) >= 0
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_readiness_endpoint_reports_critical_checks_and_json_persistence_warning():
    from backend.api import app

    client = app.test_client()
    response = client.get("/api/ready")
    assert response.status_code in {200, 503}
    payload = response.get_json()
    names = {item["name"] for item in payload["checks"]}
    assert {"patient_dataset", "model_artifacts", "models_loaded", "runtime_storage"}.issubset(names)
    persistence = next(item for item in payload["checks"] if item["name"] == "persistence_mode")
    assert persistence["status"] == "warning"
    assert payload["upgrade_stage"] == "10A"


def test_metrics_are_administrator_protected_and_record_requests():
    from backend.api import app

    reset_metrics_for_tests()
    client = app.test_client()
    denied = client.get("/api/metrics")
    assert denied.status_code == 401

    headers = _admin_headers(client)
    client.get("/api/health")
    response = client.get("/api/metrics", headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_requests"] >= 3
    assert payload["average_latency_ms"] >= 0
    assert payload["endpoint_counts"]


def test_version_endpoint_lists_stage10a_increment():
    from backend.api import app

    client = app.test_client()
    response = client.get("/api/system/version")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["app_version"] == APP_VERSION
    assert "10A" in payload["completed_stages"]


def test_secret_scanner_detects_env_and_key_patterns(tmp_path):
    (tmp_path / ".env").write_text("GROQ_API_KEY=" + "gsk_" + "1" * 30 + "\n")
    findings = scan(tmp_path)
    assert any("Forbidden release file" in finding for finding in findings)
    assert any("Groq key" in finding for finding in findings)


def test_clean_release_packager_excludes_secret_and_runtime_identity_files(tmp_path):
    project = tmp_path / "bedflow_ai"
    (project / "database").mkdir(parents=True)
    (project / "backend").mkdir()
    (project / "data").mkdir()
    (project / "backend" / "api.py").write_text("print('ok')\n")
    (project / ".env").write_text("SECRET=value\n")
    (project / "database" / "demo_users.json").write_text("[]\n")
    (project / "data" / "audit_log.json").write_text("[{\"private\": true}]\n")
    (project / "README.md").write_text("# Test\n")
    output = tmp_path / "release.zip"

    count = build_zip(project, output)
    assert count == 2
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert "bedflow_ai/.env" not in names
    assert "bedflow_ai/database/demo_users.json" not in names
    assert "bedflow_ai/data/audit_log.json" not in names
    assert "bedflow_ai/README.md" in names
    assert "bedflow_ai/backend/api.py" in names
