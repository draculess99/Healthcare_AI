"""FHIR-style interoperability adapter for the BedFlow AI demonstration.

This module creates deterministic, de-identified FHIR R4-shaped resources from the
app's proxy patient, checklist, task, prediction, and capacity data. It is not a
certified FHIR server and intentionally avoids PHI.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

FHIR_BASE = "https://bedflow.example/fhir"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_id(value: Any, prefix: str) -> str:
    raw = str(value or "unknown").strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-." else "-" for ch in raw)
    return f"{prefix}-{cleaned}"[:64]


def _reference(resource_type: str, resource_id: str) -> dict[str, str]:
    return {"reference": f"{resource_type}/{resource_id}"}


def _coding(system: str, code: str, display: str) -> dict[str, Any]:
    return {"coding": [{"system": system, "code": code, "display": display}], "text": display}


def build_patient_resource(patient: dict[str, Any]) -> dict[str, Any]:
    patient_id = _safe_id(patient.get("patient_id"), "patient")
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/Patient"]},
        "identifier": [{
            "system": "https://bedflow.example/identifier/demo-patient",
            "value": str(patient.get("patient_id", "unknown")),
        }],
        "active": True,
        "extension": [{
            "url": "https://bedflow.example/fhir/StructureDefinition/demo-data-notice",
            "valueString": "Synthetic/proxy, de-identified demonstration record; no PHI.",
        }],
    }


def build_location_resource(patient: dict[str, Any]) -> dict[str, Any]:
    unit = patient.get("unit") or patient.get("hospital_unit") or "Unknown Unit"
    location_id = _safe_id(unit, "location")
    return {
        "resourceType": "Location",
        "id": location_id,
        "status": "active",
        "name": str(unit),
        "mode": "instance",
        "physicalType": _coding("http://terminology.hl7.org/CodeSystem/location-physical-type", "wa", "Ward"),
    }


def build_encounter_resource(patient: dict[str, Any], patient_resource: dict[str, Any], location: dict[str, Any]) -> dict[str, Any]:
    encounter_id = _safe_id(patient.get("patient_id"), "encounter")
    los = float(patient.get("length_of_stay_days", 0) or 0)
    return {
        "resourceType": "Encounter",
        "id": encounter_id,
        "status": "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP", "display": "inpatient encounter"},
        "subject": _reference("Patient", patient_resource["id"]),
        "location": [{"location": _reference("Location", location["id"]), "status": "active"}],
        "length": {"value": los, "unit": "days", "system": "http://unitsofmeasure.org", "code": "d"},
        "diagnosis": [{
            "condition": {"display": str(patient.get("diagnosis_group", "Unspecified diagnosis group"))},
            "use": _coding("http://terminology.hl7.org/CodeSystem/diagnosis-role", "AD", "Admission diagnosis"),
        }],
    }


def build_observation_resources(patient: dict[str, Any], model_outputs: dict[str, Any], patient_id: str, encounter_id: str) -> list[dict[str, Any]]:
    subject = _reference("Patient", patient_id)
    encounter = _reference("Encounter", encounter_id)
    specs = [
        ("discharge-delay-risk", "Discharge delay risk probability", model_outputs.get("discharge_delay_risk_probability"), "%", 100),
        ("readmission-risk", "30-day readmission risk probability", model_outputs.get("readmission_risk_probability"), "%", 100),
        ("expected-delay-hours", "Expected discharge delay", model_outputs.get("predicted_delay_hours"), "hours", 1),
        ("bed-occupancy", "Current bed occupancy", patient.get("current_bed_occupancy_percent"), "%", 1),
        ("ed-boarding", "ED boarding count", patient.get("ed_boarding_count"), "patients", 1),
    ]
    observations = []
    for code, display, value, unit, multiplier in specs:
        if value is None or value == "":
            continue
        try:
            numeric_value = round(float(value) * multiplier, 3)
        except (TypeError, ValueError):
            continue
        observations.append({
            "resourceType": "Observation",
            "id": _safe_id(f"{patient_id}-{code}", "obs"),
            "status": "final",
            "category": [_coding("http://terminology.hl7.org/CodeSystem/observation-category", "survey", "Survey")],
            "code": _coding("https://bedflow.example/fhir/CodeSystem/bedflow-observations", code, display),
            "subject": subject,
            "encounter": encounter,
            "effectiveDateTime": _now(),
            "valueQuantity": {"value": numeric_value, "unit": unit},
            "note": [{"text": "Decision-support proxy generated by BedFlow AI; not a validated clinical measurement."}],
        })
    return observations


def build_task_resources(tasks: list[dict[str, Any]], patient_id: str, encounter_id: str) -> list[dict[str, Any]]:
    status_map = {
        "Pending": "requested", "In Progress": "in-progress", "Blocked": "on-hold",
        "Escalated": "in-progress", "Completed": "completed",
    }
    resources = []
    for task in tasks or []:
        task_id = _safe_id(task.get("task_id") or task.get("checklist_item_id"), "task")
        resources.append({
            "resourceType": "Task",
            "id": task_id,
            "status": status_map.get(str(task.get("status")), "requested"),
            "intent": "order",
            "priority": "stat" if task.get("is_overdue") else "routine",
            "code": _coding("https://bedflow.example/fhir/CodeSystem/discharge-task", str(task.get("blocker_key", "discharge-blocker")), str(task.get("title", "Discharge blocker task"))),
            "for": _reference("Patient", patient_id),
            "encounter": _reference("Encounter", encounter_id),
            "owner": {"display": str(task.get("owner_role", "Unassigned"))},
            "description": str(task.get("recommended_action") or task.get("note") or "Resolve discharge blocker."),
            "authoredOn": task.get("created_at") or _now(),
            "restriction": {"period": {"end": task.get("due_at")}} if task.get("due_at") else {},
            "note": [{"text": f"Escalation level: {task.get('escalation_level', 'None')}"}],
        })
    return resources


def build_care_plan(patient: dict[str, Any], checklist: dict[str, Any], tasks: list[dict[str, Any]], patient_id: str, encounter_id: str) -> dict[str, Any]:
    patient_key = patient.get("patient_id", "unknown")
    activities = []
    for item in (checklist or {}).get("items", []):
        if item.get("status") in {"Complete", "Not Applicable"}:
            continue
        activities.append({
            "detail": {
                "status": "not-started",
                "description": str(item.get("recommended_action", item.get("label", "Resolve discharge blocker"))),
                "performer": [{"display": str(item.get("owner_role", "Care team"))}],
            }
        })
    task_refs = [_reference("Task", _safe_id(t.get("task_id") or t.get("checklist_item_id"), "task")) for t in tasks or []]
    return {
        "resourceType": "CarePlan",
        "id": _safe_id(patient_key, "careplan"),
        "status": "active",
        "intent": "plan",
        "title": "BedFlow discharge readiness plan",
        "description": f"FHIR-style discharge plan. Readiness: {(checklist or {}).get('readiness_status', 'Unknown')}; completion: {(checklist or {}).get('completion_percent', 0)}%.",
        "subject": _reference("Patient", patient_id),
        "encounter": _reference("Encounter", encounter_id),
        "created": _now(),
        "activity": activities,
        "supportingInfo": task_refs,
    }


def build_fhir_bundle(patient: dict[str, Any], model_outputs: dict[str, Any] | None = None,
                      checklist: dict[str, Any] | None = None, tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    model_outputs = model_outputs or {}
    checklist = checklist or {}
    tasks = tasks or []
    patient_resource = build_patient_resource(patient)
    location = build_location_resource(patient)
    encounter = build_encounter_resource(patient, patient_resource, location)
    observations = build_observation_resources(patient, model_outputs, patient_resource["id"], encounter["id"])
    task_resources = build_task_resources(tasks, patient_resource["id"], encounter["id"])
    care_plan = build_care_plan(patient, checklist, tasks, patient_resource["id"], encounter["id"])
    resources = [patient_resource, location, encounter, *observations, *task_resources, care_plan]
    return {
        "resourceType": "Bundle",
        "id": _safe_id(patient.get("patient_id"), "bundle"),
        "type": "collection",
        "timestamp": _now(),
        "meta": {"tag": [{"system": "https://bedflow.example/fhir/CodeSystem/data-classification", "code": "synthetic-proxy", "display": "Synthetic/proxy demo data"}]},
        "entry": [{"fullUrl": f"{FHIR_BASE}/{r['resourceType']}/{r['id']}", "resource": r} for r in resources],
    }


def summarize_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for entry in bundle.get("entry", []):
        resource_type = entry.get("resource", {}).get("resourceType", "Unknown")
        counts[resource_type] = counts.get(resource_type, 0) + 1
    return {"bundle_id": bundle.get("id"), "resource_count": sum(counts.values()), "resource_types": counts, "generated_at": bundle.get("timestamp")}
