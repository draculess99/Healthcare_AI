"""Stage 9 capacity what-if simulation for BedFlow AI.

The simulator performs transparent counterfactual model inference. It changes
selected *operational* inputs (for example pharmacy or transport blockers),
re-scores the same synthetic/proxy patient cohort with the active XGBoost
artifacts, and compares the current and simulated operational snapshots.

It is not a causal model, live hospital capacity forecast, or clinical discharge
authorization system. Clinical stability and physician sign-off fields are
never cleared automatically by a scenario.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import threading
import uuid
from collections import defaultdict
from typing import Any, Callable

import pandas as pd

from .storage import runtime_json_path

from .command_center import (
    RISK_ORDER,
    UNIT_CAPACITY,
    build_discharge_queue,
    build_hospital_capacity_snapshot,
    infer_unit,
)

SIMULATION_RUNS_PATH = runtime_json_path("simulation_runs.json", [])
SIMULATION_UNITS = ["All Units"] + [
    unit for unit in UNIT_CAPACITY if unit != "Emergency Department"
]
_SIMULATION_LOCK = threading.Lock()

BLOCKER_FIELDS: dict[str, dict[str, str]] = {
    "pharmacy_med_rec_pending": {
        "label": "Pharmacy medication reconciliation",
        "scenario_key": "pharmacy_clearance_percent",
    },
    "insurance_authorization_pending": {
        "label": "Insurance authorization",
        "scenario_key": "insurance_clearance_percent",
    },
    "transport_pending": {
        "label": "Transport",
        "scenario_key": "transport_clearance_percent",
    },
    "home_care_setup_pending": {
        "label": "Home-care setup",
        "scenario_key": "home_care_clearance_percent",
    },
    "social_work_pending": {
        "label": "Social-work review",
        "scenario_key": "social_work_clearance_percent",
    },
}

ALL_OPERATIONAL_BLOCKERS = [
    "pharmacy_med_rec_pending",
    "insurance_authorization_pending",
    "transport_pending",
    "rehab_snf_placement_pending",
    "home_care_setup_pending",
    "social_work_pending",
    "family_pickup_pending",
]

CASE_MANAGEMENT_BLOCKERS = [
    "insurance_authorization_pending",
    "rehab_snf_placement_pending",
    "home_care_setup_pending",
    "social_work_pending",
]

PRIMARY_BOTTLENECK_ORDER = [
    ("Clinical Stability", None),
    ("Rehab/SNF", "rehab_snf_placement_pending"),
    ("Insurance", "insurance_authorization_pending"),
    ("Home Care", "home_care_setup_pending"),
    ("Pharmacy", "pharmacy_med_rec_pending"),
    ("Transport", "transport_pending"),
    ("Doctor", "doctor_signoff_pending"),
]


class SimulationValidationError(ValueError):
    """Raised when a simulation request is invalid."""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_int(value: Any, minimum: int, maximum: int, default: int = 0) -> int:
    return max(minimum, min(maximum, _to_int(value, default)))


def _atomic_write(path: str, payload: Any) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(temp_path, path)


def _load_runs(path: str = SIMULATION_RUNS_PATH) -> list[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def normalize_scenario(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    scope_unit = str(payload.get("scope_unit") or "All Units").strip()
    valid_units = set(SIMULATION_UNITS)
    if scope_unit not in valid_units:
        raise SimulationValidationError(
            f"Unknown scope_unit '{scope_unit}'. Choose All Units or a configured unit."
        )

    name = str(payload.get("scenario_name") or "Operational capacity scenario").strip()
    return {
        "scenario_name": name[:120] or "Operational capacity scenario",
        "scope_unit": scope_unit,
        "horizon_hours": _clamp_int(payload.get("horizon_hours", 24), 1, 72, 24),
        "pharmacy_clearance_percent": _clamp_int(payload.get("pharmacy_clearance_percent", 0), 0, 100),
        "insurance_clearance_percent": _clamp_int(payload.get("insurance_clearance_percent", 0), 0, 100),
        "transport_clearance_percent": _clamp_int(payload.get("transport_clearance_percent", 0), 0, 100),
        "home_care_clearance_percent": _clamp_int(payload.get("home_care_clearance_percent", 0), 0, 100),
        "social_work_clearance_percent": _clamp_int(payload.get("social_work_clearance_percent", 0), 0, 100),
        "rehab_placements_cleared": _clamp_int(payload.get("rehab_placements_cleared", 0), 0, 100),
        "additional_case_managers": _clamp_int(payload.get("additional_case_managers", 0), 0, 20),
        "cleaning_beds_released": _clamp_int(payload.get("cleaning_beds_released", 0), 0, 50),
        "temporary_beds_opened": _clamp_int(payload.get("temporary_beds_opened", 0), 0, 50),
    }


def simulation_capability() -> dict[str, Any]:
    return {
        "status": "success",
        "stage": 9,
        "mode": "counterfactual operational model inference",
        "supported_units": SIMULATION_UNITS,
        "operational_levers": [
            "Pharmacy blocker clearance",
            "Insurance authorization clearance",
            "Transport blocker clearance",
            "Home-care setup clearance",
            "Social-work clearance",
            "Rehab/SNF placements cleared",
            "Additional case-manager availability",
            "Beds released from cleaning",
            "Temporary staffed beds opened",
        ],
        "protected_safety_fields": [
            "lab_stability_flag",
            "vital_sign_stability_flag",
            "doctor_signoff_pending",
        ],
        "production_ready": False,
        "warning": (
            "Results are synthetic/proxy counterfactual estimates, not causal proof, "
            "a live ADT forecast, or authorization to discharge a patient."
        ),
    }


def _prediction_map(predictions: pd.DataFrame | list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if isinstance(predictions, pd.DataFrame):
        records = predictions.to_dict(orient="records")
    else:
        records = list(predictions or [])
    return {
        str(record.get("patient_id")): record
        for record in records
        if record.get("patient_id") is not None
    }


def _scope_mask(df: pd.DataFrame, scope_unit: str) -> pd.Series:
    if scope_unit == "All Units":
        return pd.Series(True, index=df.index)
    return df.apply(infer_unit, axis=1).eq(scope_unit)


def _priority_map(current_queue: list[dict[str, Any]]) -> dict[str, float]:
    return {
        str(item.get("patient_id")): _to_float(item.get("bed_recovery_score"), 0.0)
        for item in current_queue
    }


def _ranked_indices(
    df: pd.DataFrame,
    mask: pd.Series,
    priority: dict[str, float],
) -> list[Any]:
    candidates: list[tuple[float, str, Any]] = []
    for index in df.index[mask]:
        patient_id = str(df.at[index, "patient_id"]) if "patient_id" in df.columns else str(index)
        candidates.append((priority.get(patient_id, 0.0), patient_id, index))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in candidates]


def _count_from_percent(total: int, percent: int) -> int:
    if total <= 0 or percent <= 0:
        return 0
    return min(total, max(1, int(round(total * percent / 100.0))))


def _record_change(
    changes_by_patient: dict[str, list[str]],
    patient_id: str,
    label: str,
) -> None:
    changes_by_patient.setdefault(patient_id, [])
    if label not in changes_by_patient[patient_id]:
        changes_by_patient[patient_id].append(label)


def _clear_percent_blocker(
    working: pd.DataFrame,
    field: str,
    percent: int,
    scope: pd.Series,
    priority: dict[str, float],
    changes_by_patient: dict[str, list[str]],
) -> dict[str, Any]:
    if field not in working.columns:
        return {"eligible": 0, "changed": 0, "patient_ids": []}
    affected = scope & pd.to_numeric(working[field], errors="coerce").fillna(0).eq(1)
    ranked = _ranked_indices(working, affected, priority)
    count = _count_from_percent(len(ranked), percent)
    selected = ranked[:count]
    changed_ids: list[str] = []
    label = BLOCKER_FIELDS[field]["label"]
    for index in selected:
        working.at[index, field] = 0
        patient_id = str(working.at[index, "patient_id"]) if "patient_id" in working.columns else str(index)
        changed_ids.append(patient_id)
        _record_change(changes_by_patient, patient_id, f"Cleared {label}")
    return {
        "eligible": len(ranked),
        "changed": len(selected),
        "patient_ids": changed_ids[:25],
    }


def _clear_rehab_placements(
    working: pd.DataFrame,
    count: int,
    scope: pd.Series,
    priority: dict[str, float],
    changes_by_patient: dict[str, list[str]],
) -> dict[str, Any]:
    field = "rehab_snf_placement_pending"
    if field not in working.columns:
        return {"eligible": 0, "changed": 0, "patient_ids": []}
    affected = scope & pd.to_numeric(working[field], errors="coerce").fillna(0).eq(1)
    ranked = _ranked_indices(working, affected, priority)
    selected = ranked[: min(max(0, count), len(ranked))]
    changed_ids: list[str] = []
    for index in selected:
        working.at[index, field] = 0
        patient_id = str(working.at[index, "patient_id"]) if "patient_id" in working.columns else str(index)
        changed_ids.append(patient_id)
        _record_change(changes_by_patient, patient_id, "Cleared Rehab/SNF placement blocker")
    return {
        "eligible": len(ranked),
        "changed": len(selected),
        "patient_ids": changed_ids[:25],
    }


def _add_case_manager_capacity(
    working: pd.DataFrame,
    additional_case_managers: int,
    scope: pd.Series,
    priority: dict[str, float],
    changes_by_patient: dict[str, list[str]],
) -> dict[str, Any]:
    if "case_manager_available" not in working.columns:
        working["case_manager_available"] = 0
    dependent = pd.Series(False, index=working.index)
    for field in CASE_MANAGEMENT_BLOCKERS:
        if field in working.columns:
            dependent |= pd.to_numeric(working[field], errors="coerce").fillna(0).eq(1)
    affected = (
        scope
        & dependent
        & pd.to_numeric(working["case_manager_available"], errors="coerce").fillna(0).eq(0)
    )
    ranked = _ranked_indices(working, affected, priority)
    cases_per_added_manager = 6
    count = min(len(ranked), max(0, additional_case_managers) * cases_per_added_manager)
    selected = ranked[:count]
    changed_ids: list[str] = []
    for index in selected:
        working.at[index, "case_manager_available"] = 1
        patient_id = str(working.at[index, "patient_id"]) if "patient_id" in working.columns else str(index)
        changed_ids.append(patient_id)
        _record_change(changes_by_patient, patient_id, "Added case-manager availability")
    return {
        "eligible": len(ranked),
        "changed": len(selected),
        "patient_ids": changed_ids[:25],
        "cases_per_added_manager_assumption": cases_per_added_manager,
    }


def _clinical_stable(row: pd.Series | dict[str, Any]) -> bool:
    return (
        str(row.get("lab_stability_flag", "Stable")) == "Stable"
        and str(row.get("vital_sign_stability_flag", "Stable")) == "Stable"
    )


def _infer_primary_bottleneck(row: pd.Series | dict[str, Any]) -> str:
    if not _clinical_stable(row):
        return "Clinical Stability"
    for label, field in PRIMARY_BOTTLENECK_ORDER[1:]:
        if field and _to_int(row.get(field, 0)) == 1:
            return label
    return "None"


def _refresh_primary_bottlenecks(working: pd.DataFrame) -> None:
    working["primary_discharge_bottleneck"] = working.apply(_infer_primary_bottleneck, axis=1)


def _active_operational_blockers(row: pd.Series | dict[str, Any]) -> int:
    return sum(_to_int(row.get(field, 0)) == 1 for field in ALL_OPERATIONAL_BLOCKERS)


def _review_ready_candidate(
    row: pd.Series | dict[str, Any],
    prediction: dict[str, Any],
    horizon_hours: int,
) -> bool:
    """Identify potential expedited-review candidates, never discharge approvals."""
    return bool(
        _clinical_stable(row)
        and _to_int(row.get("doctor_signoff_pending", 0)) == 0
        and _active_operational_blockers(row) == 0
        and _to_float(prediction.get("discharge_delay_risk_probability"), 1.0) < 0.5
        and _to_float(prediction.get("predicted_delay_hours"), 999.0) <= horizon_hours
        and _to_float(prediction.get("readmission_risk_probability"), 1.0) < 0.8
    )


def _risk_is_high(level: str) -> bool:
    return str(level) in {"High", "Critical"}


def _blocker_counts(df: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in ALL_OPERATIONAL_BLOCKERS:
        counts[field] = (
            int(pd.to_numeric(df[field], errors="coerce").fillna(0).eq(1).sum())
            if field in df.columns
            else 0
        )
    return counts


def _safe_actor(actor: dict[str, Any] | None) -> dict[str, Any]:
    actor = actor or {}
    return {
        "user_id": actor.get("user_id"),
        "username": actor.get("username"),
        "display_name": actor.get("display_name"),
        "role": actor.get("role"),
    }


def run_capacity_simulation(
    patient_df: pd.DataFrame,
    current_predictions: pd.DataFrame | list[dict[str, Any]],
    scoring_fn: Callable[[pd.DataFrame], pd.DataFrame],
    scenario_payload: dict[str, Any] | None,
    current_capacity: dict[str, Any] | None = None,
    actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one operational counterfactual scenario and return a comparison."""
    if patient_df is None or patient_df.empty:
        raise SimulationValidationError("A non-empty patient dataset is required.")

    scenario = normalize_scenario(scenario_payload)
    current_df = patient_df.copy()
    working = patient_df.copy()
    current_prediction_df = (
        current_predictions.copy()
        if isinstance(current_predictions, pd.DataFrame)
        else pd.DataFrame(list(current_predictions or []))
    )
    if current_prediction_df.empty:
        current_prediction_df = scoring_fn(current_df)

    current_queue = build_discharge_queue(current_df, model_predictions=current_prediction_df)
    current_capacity = current_capacity or build_hospital_capacity_snapshot(
        current_df, model_predictions=current_prediction_df
    )
    priority = _priority_map(current_queue)
    scope = _scope_mask(working, scenario["scope_unit"])
    changes_by_patient: dict[str, list[str]] = {}
    applied_actions: dict[str, Any] = {}

    for field, metadata in BLOCKER_FIELDS.items():
        percent = scenario[metadata["scenario_key"]]
        applied_actions[metadata["scenario_key"]] = _clear_percent_blocker(
            working, field, percent, scope, priority, changes_by_patient
        )

    applied_actions["rehab_placements_cleared"] = _clear_rehab_placements(
        working,
        scenario["rehab_placements_cleared"],
        scope,
        priority,
        changes_by_patient,
    )
    applied_actions["additional_case_managers"] = _add_case_manager_capacity(
        working,
        scenario["additional_case_managers"],
        scope,
        priority,
        changes_by_patient,
    )

    # Recalculate the operational primary blocker after scenario changes. Clinical
    # stability and physician sign-off are deliberately not changed by scenarios.
    _refresh_primary_bottlenecks(working)

    simulated_prediction_df = scoring_fn(working)
    simulated_queue = build_discharge_queue(working, model_predictions=simulated_prediction_df)
    simulated_capacity_model = build_hospital_capacity_snapshot(
        working, model_predictions=simulated_prediction_df
    )

    current_predictions_by_id = _prediction_map(current_prediction_df)
    simulated_predictions_by_id = _prediction_map(simulated_prediction_df)
    current_rows = {
        str(row.get("patient_id")): row for row in current_df.to_dict(orient="records")
    }
    simulated_rows = {
        str(row.get("patient_id")): row for row in working.to_dict(orient="records")
    }

    patient_impacts: list[dict[str, Any]] = []
    current_ready = 0
    simulated_ready = 0
    current_high_critical = 0
    simulated_high_critical = 0
    patients_improved = 0
    delay_hours_removed = 0.0
    unit_accumulator: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "current_review_candidates": 0,
            "simulated_review_candidates": 0,
            "patients_improved": 0,
            "delay_hours_removed": 0.0,
            "current_high_or_critical": 0,
            "simulated_high_or_critical": 0,
            "changed_patients": 0,
        }
    )

    for patient_id, current_row in current_rows.items():
        simulated_row = simulated_rows.get(patient_id, current_row)
        current_prediction = current_predictions_by_id.get(patient_id, {})
        simulated_prediction = simulated_predictions_by_id.get(patient_id, current_prediction)
        unit = infer_unit(current_row)
        current_candidate = _review_ready_candidate(
            current_row, current_prediction, scenario["horizon_hours"]
        )
        simulated_candidate = _review_ready_candidate(
            simulated_row, simulated_prediction, scenario["horizon_hours"]
        )
        current_ready += int(current_candidate)
        simulated_ready += int(simulated_candidate)

        current_level = str(current_prediction.get("delay_risk_level", "Unknown"))
        simulated_level = str(simulated_prediction.get("delay_risk_level", "Unknown"))
        current_high_critical += int(_risk_is_high(current_level))
        simulated_high_critical += int(_risk_is_high(simulated_level))

        current_hours = _to_float(current_prediction.get("predicted_delay_hours"), 0.0)
        simulated_hours = _to_float(simulated_prediction.get("predicted_delay_hours"), current_hours)
        hours_reduction = max(0.0, current_hours - simulated_hours)
        delay_hours_removed += hours_reduction
        risk_improved = RISK_ORDER.get(simulated_level, 99) < RISK_ORDER.get(current_level, 99)
        improved = bool(risk_improved or hours_reduction >= 1.0 or (simulated_candidate and not current_candidate))
        patients_improved += int(improved)

        accumulator = unit_accumulator[unit]
        accumulator["current_review_candidates"] += int(current_candidate)
        accumulator["simulated_review_candidates"] += int(simulated_candidate)
        accumulator["patients_improved"] += int(improved)
        accumulator["delay_hours_removed"] += hours_reduction
        accumulator["current_high_or_critical"] += int(_risk_is_high(current_level))
        accumulator["simulated_high_or_critical"] += int(_risk_is_high(simulated_level))
        accumulator["changed_patients"] += int(patient_id in changes_by_patient)

        if patient_id in changes_by_patient or improved:
            patient_impacts.append(
                {
                    "patient_id": patient_id,
                    "unit": unit,
                    "changes": changes_by_patient.get(patient_id, []),
                    "current_delay_risk": current_level,
                    "simulated_delay_risk": simulated_level,
                    "current_delay_probability": round(
                        _to_float(current_prediction.get("discharge_delay_risk_probability")), 4
                    ),
                    "simulated_delay_probability": round(
                        _to_float(simulated_prediction.get("discharge_delay_risk_probability")), 4
                    ),
                    "current_predicted_delay_hours": round(current_hours, 1),
                    "simulated_predicted_delay_hours": round(simulated_hours, 1),
                    "delay_hours_removed": round(hours_reduction, 1),
                    "current_review_candidate": current_candidate,
                    "simulated_review_candidate": simulated_candidate,
                    "current_primary_bottleneck": current_row.get("primary_discharge_bottleneck", "None"),
                    "simulated_primary_bottleneck": simulated_row.get("primary_discharge_bottleneck", "None"),
                }
            )

    patient_impacts.sort(
        key=lambda item: (
            item["simulated_review_candidate"] and not item["current_review_candidate"],
            item["delay_hours_removed"],
            len(item["changes"]),
        ),
        reverse=True,
    )

    additional_model_candidates = max(0, simulated_ready - current_ready)
    cleaning_released = min(
        scenario["cleaning_beds_released"],
        _to_int(current_capacity.get("beds_pending_cleaning"), 0),
    )
    temporary_beds = scenario["temporary_beds_opened"]
    additional_capacity = additional_model_candidates + cleaning_released + temporary_beds
    current_open = _to_int(current_capacity.get("available_beds"), 0)
    current_total = _to_int(current_capacity.get("total_beds"), sum(UNIT_CAPACITY.values()))
    potential_total = current_total + temporary_beds
    potential_open = min(potential_total, current_open + additional_capacity)
    current_ed_boarders = _to_int(current_capacity.get("ed_boarders"), 0)
    potential_ed_relief = min(current_ed_boarders, additional_capacity)

    current_blockers = _blocker_counts(current_df)
    simulated_blockers = _blocker_counts(working)
    blocker_comparison = []
    label_lookup = {
        "pharmacy_med_rec_pending": "Pharmacy",
        "insurance_authorization_pending": "Insurance",
        "transport_pending": "Transport",
        "rehab_snf_placement_pending": "Rehab/SNF",
        "home_care_setup_pending": "Home care",
        "social_work_pending": "Social work",
        "family_pickup_pending": "Family pickup",
    }
    for field in ALL_OPERATIONAL_BLOCKERS:
        blocker_comparison.append(
            {
                "blocker": label_lookup[field],
                "current": current_blockers[field],
                "simulated": simulated_blockers[field],
                "removed": max(0, current_blockers[field] - simulated_blockers[field]),
            }
        )

    unit_impacts = []
    for unit in UNIT_CAPACITY:
        if unit == "Emergency Department":
            continue
        item = unit_accumulator.get(unit, {})
        unit_impacts.append(
            {
                "unit": unit,
                "current_review_candidates": int(item.get("current_review_candidates", 0)),
                "simulated_review_candidates": int(item.get("simulated_review_candidates", 0)),
                "additional_review_candidates": max(
                    0,
                    int(item.get("simulated_review_candidates", 0))
                    - int(item.get("current_review_candidates", 0)),
                ),
                "patients_improved": int(item.get("patients_improved", 0)),
                "delay_hours_removed": round(_to_float(item.get("delay_hours_removed")), 1),
                "current_high_or_critical": int(item.get("current_high_or_critical", 0)),
                "simulated_high_or_critical": int(item.get("simulated_high_or_critical", 0)),
                "changed_patients": int(item.get("changed_patients", 0)),
            }
        )

    model_versions = [
        str(value)
        for value in current_prediction_df.get("model_version", pd.Series(dtype=str)).dropna().unique().tolist()
        if str(value)
    ]

    return {
        "status": "success",
        "simulation_id": f"SIM-{uuid.uuid4().hex[:16].upper()}",
        "created_at_utc": _now_iso(),
        "actor": _safe_actor(actor),
        "scenario": scenario,
        "model_version": model_versions[0] if len(model_versions) == 1 else model_versions,
        "simulation_method": "Counterfactual feature changes followed by XGBoost re-inference",
        "summary": {
            "patients_in_scope": int(scope.sum()),
            "patients_changed": len(changes_by_patient),
            "patients_improved": patients_improved,
            "current_review_candidates": current_ready,
            "simulated_review_candidates": simulated_ready,
            "additional_review_candidates": additional_model_candidates,
            "potential_beds_recovered_from_workflow": additional_model_candidates,
            "cleaning_beds_released": cleaning_released,
            "temporary_beds_opened": temporary_beds,
            "current_open_beds": current_open,
            "potential_open_beds": potential_open,
            "additional_potential_capacity": additional_capacity,
            "delay_hours_removed": round(delay_hours_removed, 1),
            "current_high_or_critical_delay_cases": current_high_critical,
            "simulated_high_or_critical_delay_cases": simulated_high_critical,
            "high_or_critical_cases_reduced": max(0, current_high_critical - simulated_high_critical),
            "current_ed_boarders": current_ed_boarders,
            "potential_ed_boarder_reduction": potential_ed_relief,
            "current_operational_blockers": sum(current_blockers.values()),
            "simulated_operational_blockers": sum(simulated_blockers.values()),
            "operational_blockers_removed": max(
                0, sum(current_blockers.values()) - sum(simulated_blockers.values())
            ),
        },
        "applied_actions": applied_actions,
        "blocker_comparison": blocker_comparison,
        "unit_impacts": unit_impacts,
        "top_patient_impacts": patient_impacts[:25],
        "current_capacity_snapshot": current_capacity,
        "simulated_capacity_model_snapshot": simulated_capacity_model,
        "assumptions": [
            "The same active saved XGBoost artifacts score the current and simulated cohorts; no retraining occurs.",
            "Scenario levers alter operational inputs only. Lab stability, vital-sign stability, and physician sign-off are never auto-cleared.",
            "A review candidate means potentially eligible for expedited clinician review, not approved for discharge.",
            "Each added case manager is assumed to make case-manager availability visible for up to six high-priority cases; blockers are not automatically completed by that lever.",
            "One additional potentially available staffed bed is assumed to relieve at most one ED boarder.",
            "Results are counterfactual associations from synthetic/proxy data, not causal evidence or a live capacity forecast.",
        ],
        "safety": {
            "clinical_fields_modified": False,
            "automatic_discharge": False,
            "human_review_required": True,
            "production_ready": False,
        },
        "saved": False,
    }


def save_simulation_run(result: dict[str, Any], path: str = SIMULATION_RUNS_PATH) -> dict[str, Any]:
    record = dict(result)
    record["saved"] = True
    record["saved_at_utc"] = _now_iso()
    with _SIMULATION_LOCK:
        runs = _load_runs(path)
        runs.append(record)
        _atomic_write(path, runs)
    return record


def list_simulation_runs(
    limit: int = 100,
    actor_role: str | None = None,
    path: str = SIMULATION_RUNS_PATH,
) -> list[dict[str, Any]]:
    runs = _load_runs(path)
    if actor_role and actor_role != "All":
        runs = [run for run in runs if str((run.get("actor") or {}).get("role")) == actor_role]
    runs.sort(key=lambda item: str(item.get("created_at_utc", "")), reverse=True)
    return runs[: max(1, min(_to_int(limit, 100), 1000))]


def simulation_runs_csv(runs: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    fieldnames = [
        "simulation_id",
        "created_at_utc",
        "scenario_name",
        "scope_unit",
        "actor_name",
        "actor_role",
        "model_version",
        "patients_changed",
        "patients_improved",
        "additional_review_candidates",
        "potential_beds_recovered_from_workflow",
        "additional_potential_capacity",
        "delay_hours_removed",
        "potential_ed_boarder_reduction",
        "operational_blockers_removed",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for run in runs:
        scenario = run.get("scenario") or {}
        actor = run.get("actor") or {}
        summary = run.get("summary") or {}
        writer.writerow(
            {
                "simulation_id": run.get("simulation_id"),
                "created_at_utc": run.get("created_at_utc"),
                "scenario_name": scenario.get("scenario_name"),
                "scope_unit": scenario.get("scope_unit"),
                "actor_name": actor.get("display_name"),
                "actor_role": actor.get("role"),
                "model_version": run.get("model_version"),
                "patients_changed": summary.get("patients_changed"),
                "patients_improved": summary.get("patients_improved"),
                "additional_review_candidates": summary.get("additional_review_candidates"),
                "potential_beds_recovered_from_workflow": summary.get("potential_beds_recovered_from_workflow"),
                "additional_potential_capacity": summary.get("additional_potential_capacity"),
                "delay_hours_removed": summary.get("delay_hours_removed"),
                "potential_ed_boarder_reduction": summary.get("potential_ed_boarder_reduction"),
                "operational_blockers_removed": summary.get("operational_blockers_removed"),
            }
        )
    return output.getvalue()
