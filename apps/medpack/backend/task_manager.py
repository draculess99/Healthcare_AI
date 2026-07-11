"""Simple packing task lifecycle for Stage 1."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Mapping

TASK_EVENTS_PATH = "database/packing_tasks.jsonl"

TASK_STATUSES = ["NEW", "ASSIGNED", "PICKING", "PACKED", "DELIVERED", "ESCALATED", "CANCELLED"]


def _read_events() -> List[Dict[str, Any]]:
    if not os.path.exists(TASK_EVENTS_PATH):
        return []
    events: List[Dict[str, Any]] = []
    with open(TASK_EVENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _append_event(event: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(TASK_EVENTS_PATH), exist_ok=True)
    with open(TASK_EVENTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def list_tasks(limit: int = 25) -> List[Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for event in _read_events():
        task_id = event.get("task_id")
        if not task_id:
            continue
        if task_id not in latest:
            latest[task_id] = {}
        latest[task_id].update(event)
    tasks = sorted(latest.values(), key=lambda x: x.get("updated_at", x.get("created_at", "")), reverse=True)
    return tasks[:limit]


def create_task(payload: Mapping[str, Any]) -> Dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    task = {
        "task_id": f"TASK-{uuid.uuid4().hex[:8].upper()}",
        "event": "CREATE",
        "created_at": now,
        "updated_at": now,
        "status": "NEW",
        "assigned_to": payload.get("assigned_to", "Warehouse Team"),
        "item_name": payload.get("item_name", "Unknown Item"),
        "department": payload.get("department", "Unknown Department"),
        "quantity": int(float(payload.get("quantity", payload.get("recommended_pack_quantity", 1)) or 1)),
        "priority_score": float(payload.get("priority_score", 0) or 0),
        "risk_level": payload.get("risk_level", "Unknown"),
        "location": payload.get("location", ""),
        "lot_number": payload.get("lot_number", ""),
        "recommended_action": payload.get("recommended_action", "Pack and stage item."),
        "note": payload.get("note", ""),
    }
    _append_event(task)
    return task


def update_task(payload: Mapping[str, Any]) -> Dict[str, Any]:
    task_id = str(payload.get("task_id", "")).strip()
    status = str(payload.get("status", "")).strip().upper()
    if not task_id:
        raise ValueError("task_id is required")
    if status not in TASK_STATUSES:
        raise ValueError(f"Invalid status. Use one of: {', '.join(TASK_STATUSES)}")
    existing = {t["task_id"]: t for t in list_tasks(limit=500)}.get(task_id)
    if not existing:
        raise ValueError(f"Task not found: {task_id}")
    now = datetime.now().isoformat(timespec="seconds")
    event = dict(existing)
    event.update({
        "event": "STATUS_UPDATE",
        "updated_at": now,
        "status": status,
        "assigned_to": payload.get("assigned_to", existing.get("assigned_to", "Warehouse Team")),
        "note": payload.get("note", existing.get("note", "")),
    })
    _append_event(event)
    return event
