"""Discharge readiness checklist for BedFlow AI.

Stage 2 turns raw operational flags into a hospital-style discharge
readiness checklist. It does not train a new model. It converts the existing
patient fields into clear tasks, blockers, owner roles, severity levels, and
next actions that can be shown in the dashboard and used by the committee.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

SEVERITY_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_pending(patient_data: dict[str, Any], field: str) -> bool:
    return _to_int(patient_data.get(field, 0)) == 1


def _item(
    name: str,
    complete: bool,
    owner: str,
    severity: str,
    reason: str,
    action: str,
    required: bool = True,
) -> dict[str, Any]:
    """Create a normalized checklist item for UI/API display."""
    if not required:
        status = "Not Required"
        display_status = "⚪ Not Required"
    elif complete:
        status = "Complete"
        display_status = "✅ Complete"
    else:
        status = "Incomplete"
        display_status = "❌ Incomplete"

    return {
        "item": name,
        "status": status,
        "display_status": display_status,
        "complete": bool(complete or not required),
        "required": bool(required),
        "owner": owner,
        "severity": severity if required else "Low",
        "reason": reason,
        "recommended_action": action,
    }


def _risk_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    return (SEVERITY_ORDER.get(item.get("severity", "Low"), 0), item.get("item", ""))


def build_discharge_checklist(patient_data: dict[str, Any], model_outputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a hospital-style discharge readiness checklist.

    The checklist is based on the existing BedFlow synthetic/proxy fields.
    It is designed to make the UI feel like a real discharge workflow:
    clinical safety first, then physician, pharmacy, case management,
    transport, home care, social work, and family/caregiver readiness.
    """
    model_outputs = model_outputs or {}

    destination = str(patient_data.get("discharge_destination", "Home"))
    lab_stability = str(patient_data.get("lab_stability_flag", "Stable"))
    vital_stability = str(patient_data.get("vital_sign_stability_flag", "Stable"))
    med_complexity = str(patient_data.get("medication_complexity", "Low"))
    med_count = _to_int(patient_data.get("medication_count", 0))
    occupancy = _to_float(patient_data.get("current_bed_occupancy_percent", 80))
    boarders = _to_int(patient_data.get("ed_boarding_count", 0))
    readmit_prob = _to_float(model_outputs.get("readmission_risk_probability", 0))

    needs_facility = destination in {"SNF", "Rehab", "LTC"}
    needs_home_care = destination == "Home" or _is_pending(patient_data, "home_care_setup_pending")

    items: list[dict[str, Any]] = [
        _item(
            "Lab stability reviewed",
            lab_stability == "Stable",
            "Physician",
            "Critical",
            "Labs are stable." if lab_stability == "Stable" else "Lab status is unstable.",
            "Hold discharge and request physician review." if lab_stability != "Stable" else "No action needed.",
        ),
        _item(
            "Vital signs stable",
            vital_stability == "Stable",
            "Physician",
            "Critical",
            "Vital signs are stable." if vital_stability == "Stable" else "Vital signs are unstable.",
            "Hold discharge and reassess clinical readiness." if vital_stability != "Stable" else "No action needed.",
        ),
        _item(
            "Doctor discharge order / signoff",
            not _is_pending(patient_data, "doctor_signoff_pending"),
            "Physician",
            "High",
            "Discharge order is signed." if not _is_pending(patient_data, "doctor_signoff_pending") else "Physician signoff is still pending.",
            "Request discharge order/signoff from physician." if _is_pending(patient_data, "doctor_signoff_pending") else "No action needed.",
        ),
        _item(
            "Medication reconciliation",
            not _is_pending(patient_data, "pharmacy_med_rec_pending"),
            "Pharmacy",
            "High" if med_complexity == "High" or med_count >= 10 else "Medium",
            "Medication reconciliation is complete." if not _is_pending(patient_data, "pharmacy_med_rec_pending") else f"Medication reconciliation pending for {med_count} medications.",
            "Prioritize pharmacy MedRec before discharge." if _is_pending(patient_data, "pharmacy_med_rec_pending") else "No action needed.",
        ),
        _item(
            "Discharge prescriptions ready",
            not _is_pending(patient_data, "pharmacy_med_rec_pending"),
            "Pharmacy",
            "High" if med_complexity == "High" or med_count >= 10 else "Medium",
            "Discharge prescriptions are ready or not complex." if not _is_pending(patient_data, "pharmacy_med_rec_pending") else "Prescriptions may be blocked until MedRec is complete.",
            "Confirm discharge prescriptions after MedRec." if _is_pending(patient_data, "pharmacy_med_rec_pending") else "No action needed.",
        ),
        _item(
            "Transport arranged",
            not _is_pending(patient_data, "transport_pending"),
            "Transport",
            "Medium" if destination == "Home" else "High",
            "Transport is arranged." if not _is_pending(patient_data, "transport_pending") else "Transport or facility transfer is pending.",
            "Confirm transport ETA or facility pickup." if _is_pending(patient_data, "transport_pending") else "No action needed.",
        ),
        _item(
            "Insurance authorization",
            not _is_pending(patient_data, "insurance_authorization_pending"),
            "Utilization Management",
            "Critical" if needs_facility else "Medium",
            "Authorization is clear." if not _is_pending(patient_data, "insurance_authorization_pending") else "Payer authorization is pending.",
            "Escalate authorization with payer/UM team." if _is_pending(patient_data, "insurance_authorization_pending") else "No action needed.",
            required=needs_facility or _is_pending(patient_data, "insurance_authorization_pending"),
        ),
        _item(
            "Rehab/SNF placement confirmed",
            not _is_pending(patient_data, "rehab_snf_placement_pending"),
            "Case Manager",
            "Critical",
            "Facility placement is confirmed." if not _is_pending(patient_data, "rehab_snf_placement_pending") else "Rehab/SNF placement is still pending.",
            "Escalate facility bed search/placement." if _is_pending(patient_data, "rehab_snf_placement_pending") else "No action needed.",
            required=needs_facility,
        ),
        _item(
            "Home care setup",
            not _is_pending(patient_data, "home_care_setup_pending"),
            "Case Manager",
            "High",
            "Home care is set up or not needed." if not _is_pending(patient_data, "home_care_setup_pending") else "Home-care agency setup is pending.",
            "Expedite home-health agency intake." if _is_pending(patient_data, "home_care_setup_pending") else "No action needed.",
            required=needs_home_care,
        ),
        _item(
            "Social work review",
            not _is_pending(patient_data, "social_work_pending"),
            "Social Worker",
            "Medium",
            "Social work review is complete or not needed." if not _is_pending(patient_data, "social_work_pending") else "Social work review is pending.",
            "Request social work review for discharge barriers." if _is_pending(patient_data, "social_work_pending") else "No action needed.",
            required=_is_pending(patient_data, "social_work_pending"),
        ),
        _item(
            "Family/caregiver pickup or support confirmed",
            not _is_pending(patient_data, "family_pickup_pending"),
            "Family / Case Manager",
            "Medium",
            "Family/caregiver support is confirmed or not needed." if not _is_pending(patient_data, "family_pickup_pending") else "Family pickup/caregiver support is pending.",
            "Contact family/caregiver and confirm pickup/support plan." if _is_pending(patient_data, "family_pickup_pending") else "No action needed.",
            required=destination == "Home" or _is_pending(patient_data, "family_pickup_pending"),
        ),
        _item(
            "Case manager available",
            _to_int(patient_data.get("case_manager_available", 1)) == 1,
            "Case Manager",
            "High",
            "Case manager is available." if _to_int(patient_data.get("case_manager_available", 1)) == 1 else "Case manager is unavailable.",
            "Assign case manager coverage or escalate to bed-flow lead." if _to_int(patient_data.get("case_manager_available", 1)) != 1 else "No action needed.",
        ),
    ]

    blockers = [item for item in items if item["status"] == "Incomplete"]
    blockers.sort(key=_risk_sort_key, reverse=True)

    total_count = len(items)
    completed_count = sum(1 for item in items if item["complete"])
    completion_percent = round((completed_count / total_count) * 100) if total_count else 0

    critical_count = sum(1 for item in blockers if item["severity"] == "Critical")
    high_count = sum(1 for item in blockers if item["severity"] == "High")
    medium_count = sum(1 for item in blockers if item["severity"] == "Medium")

    clinical_blocked = any(
        item["item"] in {"Lab stability reviewed", "Vital signs stable"} and item["status"] == "Incomplete"
        for item in items
    )
    high_bed_pressure = occupancy >= 90 or boarders >= 8

    if clinical_blocked:
        readiness_status = "Not Clinically Ready"
        readiness_color = "red"
    elif critical_count > 0 and high_bed_pressure:
        readiness_status = "Escalate Now"
        readiness_color = "red"
    elif critical_count > 0 or high_count > 0:
        readiness_status = "Blocked"
        readiness_color = "orange"
    elif medium_count > 0:
        readiness_status = "Almost Ready"
        readiness_color = "yellow"
    else:
        readiness_status = "Ready for Discharge"
        readiness_color = "green"

    owner_counts = Counter(item["owner"] for item in blockers)
    owner_summary = [
        {"owner": owner, "active_blockers": count}
        for owner, count in owner_counts.most_common()
    ]

    if blockers:
        top = blockers[0]
        readiness_summary = (
            f"{readiness_status}: {len(blockers)} active blocker(s). "
            f"Top blocker: {top['item']} owned by {top['owner']} ({top['severity']})."
        )
    else:
        readiness_summary = "Ready for Discharge: all discharge readiness checks are complete or not required."

    return {
        "readiness_status": readiness_status,
        "readiness_color": readiness_color,
        "readiness_summary": readiness_summary,
        "completed_count": completed_count,
        "total_count": total_count,
        "completion_percent": completion_percent,
        "critical_blocker_count": critical_count,
        "high_blocker_count": high_count,
        "medium_blocker_count": medium_count,
        "active_blocker_count": len(blockers),
        "blockers": blockers,
        "blocker_names": [item["item"] for item in blockers],
        "owner_summary": owner_summary,
        "checklist": items,
        "uses_model_outputs": bool(model_outputs),
        "readmission_probability_used": readmit_prob,
    }


def checklist_action_items(checklist: dict[str, Any], max_items: int = 5) -> list[str]:
    """Return concise action-plan lines from the most important blockers."""
    actions: list[str] = []
    for blocker in checklist.get("blockers", [])[:max_items]:
        actions.append(
            f"{blocker['owner']}: {blocker['recommended_action']} ({blocker['item']}, {blocker['severity']})."
        )
    return actions
