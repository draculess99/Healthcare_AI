from __future__ import annotations

import json

from backend.auth import DEFAULT_DEMO_PASSWORD, can_update_task, sanitize_user
from backend.tasks import list_task_events, update_task_status


def _user(role: str):
    return sanitize_user(
        {
            "user_id": f"USR-{role}",
            "username": role.lower().replace(" ", ""),
            "display_name": f"Demo {role}",
            "role": role,
            "department": "Test",
            "active": True,
        }
    )


def test_task_permission_matches_owner_or_supervisor():
    pharmacy_task = {"task_id": "T-1", "owner_role": "Pharmacy"}
    assert can_update_task(_user("Pharmacist"), pharmacy_task) is True
    assert can_update_task(_user("Nurse"), pharmacy_task) is False
    assert can_update_task(_user("Bed Manager"), pharmacy_task) is True
    assert can_update_task(_user("Administrator"), pharmacy_task) is True


def test_task_update_creates_immutable_event(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.json"
    events_path = tmp_path / "task_events.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "task_id": "TASK-1",
                    "patient_id": "P-1",
                    "task_type": "Medication reconciliation",
                    "owner_role": "Pharmacy",
                    "status": "Pending",
                    "severity": "High",
                    "created_at": "2026-07-11T00:00:00+00:00",
                    "sla_minutes": 120,
                    "notes": [],
                }
            ]
        )
    )
    monkeypatch.setattr("backend.tasks.TASKS_PATH", str(tasks_path))
    monkeypatch.setattr("backend.tasks.TASK_EVENTS_PATH", str(events_path))

    task = update_task_status(
        "TASK-1",
        "Completed",
        note="Medication list reconciled.",
        updated_by="Taylor Chen, PharmD",
        updated_by_role="Pharmacist",
        updated_by_user_id="USR-PHARM",
    )

    assert task["status"] == "Completed"
    events = list_task_events(task_id="TASK-1")
    assert len(events) == 1
    assert events[0]["old_status"] == "Pending"
    assert events[0]["new_status"] == "Completed"
    assert events[0]["actor_role"] == "Pharmacist"
    assert events[0]["event_id"].startswith("TEVT-")


def test_login_returns_signed_identity_and_permissions():
    from backend.api import app

    client = app.test_client()
    response = client.post(
        "/api/auth/login",
        json={"username": "bedmanager", "password": DEFAULT_DEMO_PASSWORD},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["token"]
    assert payload["user"]["role"] == "Bed Manager"
    assert "task.update_any" in payload["user"]["permissions"]

    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {payload['token']}"},
    )
    assert me.status_code == 200
    assert me.get_json()["user"]["username"] == "bedmanager"


def test_api_enforces_task_owner_role(tmp_path, monkeypatch):
    from backend.api import app

    tasks_path = tmp_path / "tasks.json"
    events_path = tmp_path / "task_events.json"
    tasks_path.write_text(
        json.dumps(
            [
                {
                    "task_id": "TASK-PHARM-1",
                    "patient_id": "P-2",
                    "task_type": "Medication reconciliation",
                    "owner_role": "Pharmacy",
                    "status": "Pending",
                    "severity": "High",
                    "created_at": "2026-07-11T00:00:00+00:00",
                    "sla_minutes": 120,
                    "notes": [],
                }
            ]
        )
    )
    monkeypatch.setattr("backend.tasks.TASKS_PATH", str(tasks_path))
    monkeypatch.setattr("backend.tasks.TASK_EVENTS_PATH", str(events_path))

    client = app.test_client()

    nurse_login = client.post(
        "/api/auth/login",
        json={"username": "nurse", "password": DEFAULT_DEMO_PASSWORD},
    ).get_json()
    nurse_response = client.post(
        "/api/tasks/update_status",
        json={"task_id": "TASK-PHARM-1", "status": "Completed", "note": "Attempted update"},
        headers={"Authorization": f"Bearer {nurse_login['token']}"},
    )
    assert nurse_response.status_code == 403

    pharmacist_login = client.post(
        "/api/auth/login",
        json={"username": "pharmacist", "password": DEFAULT_DEMO_PASSWORD},
    ).get_json()
    pharmacist_response = client.post(
        "/api/tasks/update_status",
        json={"task_id": "TASK-PHARM-1", "status": "Completed", "note": "Verified"},
        headers={"Authorization": f"Bearer {pharmacist_login['token']}"},
    )
    assert pharmacist_response.status_code == 200
    assert pharmacist_response.get_json()["task"]["last_updated_by_role"] == "Pharmacist"
    assert list_task_events(task_id="TASK-PHARM-1")[0]["actor_role"] == "Pharmacist"
