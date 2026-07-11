"""Append-only audit records for human-supervised BedFlow decisions.

This remains a persistent JSON-backed portfolio implementation. Public demos
should use a mounted runtime directory and a single application instance.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import uuid
from typing import Any

from .storage import runtime_json_path

AUDIT_LOG_PATH = runtime_json_path("audit_log.json", [])


def init_audit_log() -> None:
    if not os.path.exists(AUDIT_LOG_PATH):
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
        with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def _load_log() -> list[dict[str, Any]]:
    init_audit_log()
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_log(records: list[dict[str, Any]]) -> None:
    init_audit_log()
    temp_path = f"{AUDIT_LOG_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    os.replace(temp_path, AUDIT_LOG_PATH)


def log_human_decision(
    patient_id: str,
    model_outputs: dict[str, Any],
    research_outputs: dict[str, Any],
    committee_rec: str,
    human_decision: str,
    human_note: str,
    memory_insight: Any,
    discharge_checklist: dict[str, Any] | None = None,
    task_snapshot: list[dict[str, Any]] | None = None,
    model_explanations: dict[str, Any] | None = None,
    reviewer_name: str = "",
    reviewer_role: str = "",
    reviewer_user_id: str | None = None,
    authentication_source: str = "local-demo-rbac",
    model_version: str | None = None,
) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    model_outputs = model_outputs or {}
    research_outputs = research_outputs or {}
    record = {
        "audit_id": f"AUD-{uuid.uuid4().hex[:16].upper()}",
        "timestamp_utc": now,
        # Backward-compatible display field used by older dashboards.
        "timestamp": now,
        "patient_id": patient_id,
        "reviewer_name": reviewer_name,
        "reviewer_role": reviewer_role,
        "reviewer_user_id": reviewer_user_id,
        "authentication_source": authentication_source,
        "model_version": model_version or model_outputs.get("model_version"),
        "model_outputs": model_outputs,
        "research_outputs": research_outputs,
        "committee_recommendation": committee_rec,
        "human_decision": human_decision,
        "human_note": human_note,
        "risk_level": model_outputs.get("delay_risk_level", "Unknown"),
        "readmission_risk_level": model_outputs.get("readmission_risk_level", "Unknown"),
        "bed_capacity_impact": research_outputs.get("bed_capacity", {}).get(
            "bed_pressure_level", "Unknown"
        ),
        "memory_insight": memory_insight,
        "discharge_checklist": discharge_checklist,
        "task_snapshot": task_snapshot or [],
        "model_explanations": model_explanations,
    }

    records = _load_log()
    records.append(record)
    _save_log(records)
    return record


def get_audit_log() -> list[dict[str, Any]]:
    return _load_log()
