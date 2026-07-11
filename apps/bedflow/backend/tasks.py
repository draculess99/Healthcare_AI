"""Task ownership and escalation workflow for BedFlow AI.

Stage 3 converts discharge blockers into operational tasks with owners,
statuses, SLA timers, overdue flags, and escalation levels. This is still a
persistent JSON-backed demonstration layer, not a production workflow engine.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from typing import Any

from .storage import runtime_json_path

TASKS_PATH = runtime_json_path("tasks.json", [])
TASK_EVENTS_PATH = runtime_json_path("task_events.json", [])

VALID_STATUSES = [
    "Not Started",
    "Pending",
    "In Progress",
    "Blocked",
    "Completed",
    "Escalated",
]

ACTIVE_STATUSES = {"Not Started", "Pending", "In Progress", "Blocked", "Escalated"}

# Practical demo SLAs. These are operational placeholders, not hospital policy.
SLA_BY_OWNER = {
    "Physician": 90,
    "Pharmacy": 120,
    "Transport": 90,
    "Utilization Management": 240,
    "Case Manager": 240,
    "Social Worker": 180,
    "Family / Case Manager": 180,
}

SLA_BY_ITEM_KEYWORD = {
    "lab": 60,
    "vital": 60,
    "doctor": 90,
    "medication": 120,
    "prescription": 120,
    "transport": 90,
    "insurance": 240,
    "rehab": 360,
    "snf": 360,
    "home care": 240,
    "social": 180,
    "family": 180,
    "case manager": 120,
}

SEVERITY_RANK = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}


def _ensure_store() -> None:
    os.makedirs(os.path.dirname(TASKS_PATH), exist_ok=True)
    if not os.path.exists(TASKS_PATH):
        with open(TASKS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def _load_raw_tasks() -> list[dict[str, Any]]:
    _ensure_store()
    try:
        with open(TASKS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_raw_tasks(tasks: list[dict[str, Any]]) -> None:
    _ensure_store()
    temp_path = f"{TASKS_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)
    os.replace(temp_path, TASKS_PATH)


def _ensure_event_store() -> None:
    os.makedirs(os.path.dirname(TASK_EVENTS_PATH), exist_ok=True)
    if not os.path.exists(TASK_EVENTS_PATH):
        with open(TASK_EVENTS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def _load_task_events() -> list[dict[str, Any]]:
    _ensure_event_store()
    try:
        with open(TASK_EVENTS_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _append_task_event(event: dict[str, Any]) -> dict[str, Any]:
    events = _load_task_events()
    events.append(event)
    temp_path = f"{TASK_EVENTS_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)
    os.replace(temp_path, TASK_EVENTS_PATH)
    return event


def record_task_event(
    task: dict[str, Any],
    event_type: str,
    old_status: str | None = None,
    new_status: str | None = None,
    note: str = "",
    actor_name: str = "System",
    actor_role: str = "System",
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Append an immutable task lifecycle event."""
    event = {
        "event_id": f"TEVT-{uuid.uuid4().hex[:16].upper()}",
        "timestamp_utc": _iso_now(),
        "event_type": event_type,
        "task_id": task.get("task_id"),
        "patient_id": task.get("patient_id"),
        "task_type": task.get("task_type"),
        "owner_role": task.get("owner_role"),
        "old_status": old_status,
        "new_status": new_status,
        "note": note,
        "actor_name": actor_name,
        "actor_role": actor_role,
        "actor_user_id": actor_user_id,
    }
    return _append_task_event(event)


def list_task_events(
    patient_id: str | None = None,
    task_id: str | None = None,
    actor_role: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    events = _load_task_events()
    if patient_id:
        events = [event for event in events if str(event.get("patient_id")) == str(patient_id)]
    if task_id:
        events = [event for event in events if str(event.get("task_id")) == str(task_id)]
    if actor_role and actor_role != "All":
        events = [event for event in events if str(event.get("actor_role")) == str(actor_role)]
    events.sort(key=lambda event: str(event.get("timestamp_utc", "")), reverse=True)
    return events[: max(1, min(int(limit), 5000))]


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _iso_now() -> str:
    return _now_utc().isoformat(timespec="seconds")


def _parse_dt(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.timezone.utc)
        return parsed
    except ValueError:
        return None




def _infer_unit(patient_data: dict[str, Any]) -> str:
    diagnosis = str(patient_data.get("diagnosis_group", "General Medicine"))
    acuity = str(patient_data.get("acuity_level", "Medium"))
    if acuity == "High" and diagnosis in {"Cardiology", "Pulmonology", "Neurology"}:
        return "ICU"
    if diagnosis in {"Cardiology", "Pulmonology", "Neurology"}:
        return "Telemetry"
    if diagnosis == "Oncology":
        return "Oncology"
    if diagnosis == "Orthopedics":
        return "Orthopedics"
    return "Med/Surg"

def _slug(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(text).strip().lower()).strip("-")
    return text[:48] or "task"


def _stable_task_id(patient_id: str, checklist_item: str) -> str:
    return f"TASK-{patient_id}-{_slug(checklist_item)}"


def _sla_minutes(blocker: dict[str, Any]) -> int:
    item = str(blocker.get("item", "")).lower()
    owner = str(blocker.get("owner", ""))
    severity = str(blocker.get("severity", "Medium"))

    for keyword, minutes in SLA_BY_ITEM_KEYWORD.items():
        if keyword in item:
            base = minutes
            break
    else:
        base = SLA_BY_OWNER.get(owner, 180)

    if severity == "Critical":
        return min(base, 180)
    if severity == "High":
        return min(base, 240)
    return base


def _runtime(task: dict[str, Any]) -> dict[str, Any]:
    status = task.get("status", "Pending")
    created_at = _parse_dt(task.get("created_at")) or _now_utc()
    completed_at = _parse_dt(task.get("completed_at"))
    now = _now_utc()
    end_time = completed_at if status == "Completed" and completed_at else now
    minutes_waiting = max(0, int((end_time - created_at).total_seconds() // 60))
    sla = int(task.get("sla_minutes") or 180)
    due_at = created_at + _dt.timedelta(minutes=sla)
    minutes_until_due = int((due_at - now).total_seconds() // 60)
    overdue = status in ACTIVE_STATUSES and minutes_until_due < 0

    severity = str(task.get("severity", "Medium"))
    if status == "Escalated" or overdue or severity == "Critical":
        escalation_level = "Critical" if severity == "Critical" or overdue else "High"
    elif severity == "High":
        escalation_level = "High"
    elif severity == "Medium":
        escalation_level = "Medium"
    else:
        escalation_level = "Routine"

    enriched = dict(task)
    enriched.update(
        {
            "minutes_waiting": minutes_waiting,
            "due_at": due_at.isoformat(timespec="seconds"),
            "minutes_until_due": minutes_until_due,
            "overdue": overdue,
            "escalation_level": escalation_level,
            "is_active": status in ACTIVE_STATUSES,
        }
    )
    return enriched


def _task_from_blocker(patient_data: dict[str, Any], blocker: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    patient_id = str(patient_data.get("patient_id", "UNKNOWN"))
    item = str(blocker.get("item", "Discharge blocker"))
    task_id = _stable_task_id(patient_id, item)
    existing = existing or {}

    current_status = existing.get("status", "Pending")
    if current_status not in VALID_STATUSES:
        current_status = "Pending"

    now = _iso_now()
    task = {
        "task_id": task_id,
        "patient_id": patient_id,
        "unit": patient_data.get("unit") or patient_data.get("inferred_unit") or _infer_unit(patient_data),
        "diagnosis_group": patient_data.get("diagnosis_group", "Unknown"),
        "task_type": item,
        "source_checklist_item": item,
        "owner_role": blocker.get("owner", "Bed Manager"),
        "status": current_status,
        "severity": blocker.get("severity", "Medium"),
        "reason": blocker.get("reason", ""),
        "recommended_action": blocker.get("recommended_action", "Review discharge blocker."),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "completed_at": existing.get("completed_at"),
        "sla_minutes": existing.get("sla_minutes") or _sla_minutes(blocker),
        "notes": existing.get("notes", []),
        "source": "Discharge Readiness Checklist",
    }

    if task["status"] == "Completed" and not task.get("completed_at"):
        task["completed_at"] = now
    if task["status"] != "Completed":
        task["completed_at"] = None

    return _runtime(task)


def list_tasks(
    patient_id: str | None = None,
    owner: str | None = None,
    status: str | None = None,
    include_completed: bool = True,
) -> list[dict[str, Any]]:
    tasks = [_runtime(task) for task in _load_raw_tasks()]
    if patient_id:
        tasks = [task for task in tasks if str(task.get("patient_id")) == str(patient_id)]
    if owner and owner != "All":
        tasks = [task for task in tasks if str(task.get("owner_role")) == str(owner)]
    if status and status != "All":
        tasks = [task for task in tasks if str(task.get("status")) == str(status)]
    if not include_completed:
        tasks = [task for task in tasks if task.get("status") != "Completed"]
    tasks.sort(
        key=lambda task: (
            task.get("overdue", False),
            SEVERITY_RANK.get(task.get("severity", "Medium"), 0),
            task.get("minutes_waiting", 0),
        ),
        reverse=True,
    )
    return tasks


def sync_tasks_from_checklist(patient_data: dict[str, Any], checklist: dict[str, Any]) -> dict[str, Any]:
    """Create or refresh patient tasks from active checklist blockers.

    This preserves task status and notes for existing task IDs. Completed tasks
    remain completed even if the synthetic patient source still says the raw
    blocker is pending; that lets a demo user mark work as done.
    """
    patient_id = str(patient_data.get("patient_id", "UNKNOWN"))
    raw_tasks = _load_raw_tasks()
    existing_by_id = {task.get("task_id"): task for task in raw_tasks}
    task_ids_for_patient = set()
    created = 0
    refreshed = 0

    for blocker in checklist.get("blockers", []):
        item = str(blocker.get("item", "Discharge blocker"))
        task_id = _stable_task_id(patient_id, item)
        previous = existing_by_id.get(task_id)
        if previous:
            refreshed += 1
        else:
            created += 1
        task = _task_from_blocker(patient_data, blocker, previous)
        existing_by_id[task_id] = task
        if not previous:
            record_task_event(
                task,
                event_type="Task Created",
                old_status=None,
                new_status=task.get("status"),
                note="Created from discharge-readiness checklist blocker.",
                actor_name="BedFlow Workflow Engine",
                actor_role="System",
            )
        task_ids_for_patient.add(task_id)

    merged = list(existing_by_id.values())
    _save_raw_tasks(merged)
    patient_tasks = list_tasks(patient_id=patient_id)
    return {
        "status": "success",
        "patient_id": patient_id,
        "created_count": created,
        "refreshed_count": refreshed,
        "active_blocker_count": len(checklist.get("blockers", [])),
        "patient_tasks": patient_tasks,
        "summary": summarize_tasks(patient_tasks),
    }


def update_task_status(
    task_id: str,
    status: str,
    note: str = "",
    updated_by: str = "Bed Manager",
    updated_by_role: str | None = None,
    updated_by_user_id: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid statuses: {', '.join(VALID_STATUSES)}")

    raw_tasks = _load_raw_tasks()
    now = _iso_now()
    found = False
    updated_task: dict[str, Any] | None = None
    old_status: str | None = None

    for task in raw_tasks:
        if task.get("task_id") == task_id:
            found = True
            old_status = str(task.get("status", "Pending"))
            task["status"] = status
            task["updated_at"] = now
            task["last_updated_by"] = updated_by
            task["last_updated_by_role"] = updated_by_role or updated_by
            task["last_updated_by_user_id"] = updated_by_user_id
            if status == "Completed":
                task["completed_at"] = now
            elif status in ACTIVE_STATUSES:
                task["completed_at"] = None

            task.setdefault("notes", [])
            if note:
                task["notes"].append(
                    {
                        "timestamp": now,
                        "updated_by": updated_by,
                        "updated_by_role": updated_by_role or updated_by,
                        "updated_by_user_id": updated_by_user_id,
                        "status": status,
                        "note": note,
                    }
                )
            updated_task = _runtime(task)
            break

    if not found:
        raise KeyError(f"Task not found: {task_id}")

    _save_raw_tasks(raw_tasks)
    if updated_task:
        record_task_event(
            updated_task,
            event_type="Status Updated",
            old_status=old_status,
            new_status=status,
            note=note,
            actor_name=updated_by,
            actor_role=updated_by_role or updated_by,
            actor_user_id=updated_by_user_id,
        )
    return updated_task or {}


def get_overdue_tasks() -> list[dict[str, Any]]:
    return [task for task in list_tasks(include_completed=False) if task.get("overdue")]


def summarize_tasks(tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tasks = list_tasks() if tasks is None else [_runtime(task) for task in tasks]
    active = [task for task in tasks if task.get("status") in ACTIVE_STATUSES]
    overdue = [task for task in active if task.get("overdue")]
    completed = [task for task in tasks if task.get("status") == "Completed"]
    escalated = [task for task in active if task.get("status") == "Escalated" or task.get("escalation_level") in {"Critical", "High"}]

    by_owner = Counter(task.get("owner_role", "Unknown") for task in active)
    by_status = Counter(task.get("status", "Unknown") for task in tasks)
    by_severity = Counter(task.get("severity", "Unknown") for task in active)

    role_rows = []
    for owner, count in by_owner.most_common():
        owner_tasks = [task for task in active if task.get("owner_role") == owner]
        role_rows.append(
            {
                "owner_role": owner,
                "active_tasks": count,
                "overdue_tasks": sum(1 for task in owner_tasks if task.get("overdue")),
                "critical_or_high": sum(1 for task in owner_tasks if task.get("severity") in {"Critical", "High"}),
            }
        )

    return {
        "total_tasks": len(tasks),
        "active_tasks": len(active),
        "completed_tasks": len(completed),
        "overdue_tasks": len(overdue),
        "escalated_tasks": len(escalated),
        "by_owner": dict(by_owner),
        "by_status": dict(by_status),
        "by_severity": dict(by_severity),
        "role_rows": role_rows,
    }


def build_task_plan_preview(patient_data: dict[str, Any], checklist: dict[str, Any]) -> list[dict[str, Any]]:
    """Return unsaved task previews for checklist blockers."""
    return [
        _task_from_blocker(patient_data, blocker, existing=None)
        for blocker in checklist.get("blockers", [])
    ]
