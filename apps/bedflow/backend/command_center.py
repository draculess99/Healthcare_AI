"""Hospital command-center helpers for BedFlow AI.

The command center combines two clearly separated layers:

1. A simulated/proxy hospital capacity snapshot for portfolio demonstration.
2. Patient-level XGBoost predictions loaded from the published model artifacts.

The queue never trains models and never uses known outcome/target columns to
rank current patients. If model scoring is temporarily unavailable, it falls
back to conservative operational heuristics that use only information that
would be available at review time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


UNIT_CAPACITY = {
    "Emergency Department": 40,
    "ICU": 20,
    "Telemetry": 35,
    "Med/Surg": 80,
    "Oncology": 25,
    "Orthopedics": 30,
}

RISK_ORDER = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
RISK_PROBABILITY_FALLBACK = {"Low": 0.15, "Medium": 0.35, "High": 0.65, "Critical": 0.88}

OWNER_BY_BOTTLENECK = {
    "Clinical Stability": "Physician",
    "Doctor": "Physician",
    "Home Care": "Case Manager",
    "Insurance": "Utilization Management",
    "None": "Bed Manager",
    "Pharmacy": "Pharmacy",
    "Rehab/SNF": "Case Manager",
    "Transport": "Transport",
}

NEXT_ACTION_BY_BOTTLENECK = {
    "Clinical Stability": "Request physician safety review",
    "Doctor": "Request discharge order/sign-off",
    "Home Care": "Confirm home-health agency and support plan",
    "Insurance": "Escalate authorization with payer/UM team",
    "None": "Progress routine discharge workflow",
    "Pharmacy": "Prioritize medication reconciliation",
    "Rehab/SNF": "Escalate facility placement or bed confirmation",
    "Transport": "Confirm transport or family pickup ETA",
}


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


def _risk_badge(level: str) -> str:
    badges = {
        "Critical": "🔴 Critical",
        "High": "🟠 High",
        "Medium": "🟡 Medium",
        "Low": "🟢 Low",
    }
    return badges.get(level, level)


def _percentage(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{max(0.0, min(1.0, float(value))) * 100:.0f}%"


def infer_unit(row: pd.Series | dict[str, Any]) -> str:
    """Infer a demonstration unit because the source data has no ward field."""
    diagnosis = str(row.get("diagnosis_group", "General Medicine"))
    acuity = str(row.get("acuity_level", "Medium"))

    if acuity == "High" and diagnosis in {"Cardiology", "Pulmonology", "Neurology"}:
        return "ICU"
    if diagnosis in {"Cardiology", "Pulmonology", "Neurology"}:
        return "Telemetry"
    if diagnosis == "Oncology":
        return "Oncology"
    if diagnosis == "Orthopedics":
        return "Orthopedics"
    return "Med/Surg"


def pressure_level_from_occupancy(occupancy_percent: float, ed_boarders: int = 0) -> str:
    if occupancy_percent >= 95 or ed_boarders > 10:
        return "Critical"
    if occupancy_percent >= 85 or ed_boarders >= 6:
        return "High"
    if occupancy_percent >= 75:
        return "Medium"
    return "Low"


def estimate_delay_hours_fallback(row: pd.Series | dict[str, Any]) -> float:
    """Prospective operational fallback that excludes outcome/target columns."""
    score = 1.0
    score += min(_to_float(row.get("length_of_stay_days", 0)), 20) * 0.35
    score += 3.0 * _to_int(row.get("doctor_signoff_pending", 0))
    score += 3.5 * _to_int(row.get("pharmacy_med_rec_pending", 0))
    score += 2.5 * _to_int(row.get("transport_pending", 0))
    score += 6.0 * _to_int(row.get("insurance_authorization_pending", 0))
    score += 8.0 * _to_int(row.get("rehab_snf_placement_pending", 0))
    score += 4.0 * _to_int(row.get("home_care_setup_pending", 0))
    score += 3.0 * _to_int(row.get("social_work_pending", 0))
    score += 2.0 * _to_int(row.get("weekend_discharge_flag", 0))
    score += 1.5 * _to_int(row.get("after_hours_flag", 0))

    if str(row.get("lab_stability_flag", "Stable")) == "Unstable":
        score += 6.0
    if str(row.get("vital_sign_stability_flag", "Stable")) == "Unstable":
        score += 6.0
    if _to_float(row.get("current_bed_occupancy_percent", 0)) >= 90:
        score += 2.0
    score += min(_to_int(row.get("ed_boarding_count", 0)), 20) * 0.15
    return round(min(max(score, 0.0), 36.0), 1)


def estimate_delay_risk(row: pd.Series | dict[str, Any]) -> str:
    """Fallback delay band using only prospective operational inputs."""
    hours = estimate_delay_hours_fallback(row)
    unstable = (
        str(row.get("lab_stability_flag", "Stable")) == "Unstable"
        or str(row.get("vital_sign_stability_flag", "Stable")) == "Unstable"
    )
    if unstable or hours >= 18:
        return "Critical"
    if hours >= 10:
        return "High"
    if hours >= 5:
        return "Medium"
    return "Low"


def estimate_readmission_risk(row: pd.Series | dict[str, Any]) -> str:
    """Fallback readmission band without using readmitted_30_days."""
    points = 0
    points += min(_to_int(row.get("prior_readmissions_12mo", 0)), 3) * 3
    points += min(_to_int(row.get("prior_admissions_6mo", 0)), 5)
    points += min(_to_int(row.get("prior_ed_visits_6mo", 0)), 5)
    points += 2 if _to_int(row.get("medication_count", 0)) >= 12 else 0
    points += 1 if _to_int(row.get("medication_count", 0)) >= 8 else 0
    points += 2 if _to_int(row.get("lives_alone", 0)) else 0
    points += 2 if str(row.get("home_support_level", "Good")) == "Limited" else 0
    points += 3 if str(row.get("lab_stability_flag", "Stable")) == "Unstable" else 0
    points += 3 if str(row.get("vital_sign_stability_flag", "Stable")) == "Unstable" else 0
    points += 1 if _to_int(row.get("age", 0)) >= 75 else 0

    if points >= 13:
        return "Critical"
    if points >= 8:
        return "High"
    if points >= 4:
        return "Medium"
    return "Low"


def bottleneck_owner(bottleneck: str) -> str:
    return OWNER_BY_BOTTLENECK.get(str(bottleneck), "Bed Manager")


def bottleneck_next_action(bottleneck: str) -> str:
    return NEXT_ACTION_BY_BOTTLENECK.get(str(bottleneck), "Review discharge plan")


def estimate_case_status(row: pd.Series | dict[str, Any], delay_risk: str, readmission_risk: str) -> str:
    bottleneck = str(row.get("primary_discharge_bottleneck", "None"))
    if delay_risk == "Critical" or readmission_risk == "Critical":
        return "Escalate Now"
    if bottleneck not in {"None", ""} and delay_risk in {"High", "Critical"}:
        return "Blocked"
    if delay_risk == "Medium" or readmission_risk == "Medium":
        return "Needs Review"
    return "Ready / Routine"


def bed_recovery_score(
    row: pd.Series | dict[str, Any],
    delay_risk: str,
    readmission_risk: str,
    predicted_delay_hours: float | None = None,
) -> float:
    hours = (
        estimate_delay_hours_fallback(row)
        if predicted_delay_hours is None
        else max(0.0, _to_float(predicted_delay_hours))
    )
    occ = _to_float(row.get("current_bed_occupancy_percent", 80))
    boarders = _to_int(row.get("ed_boarding_count", 0))
    bottleneck = str(row.get("primary_discharge_bottleneck", "None"))

    score = 0.0
    score += min(hours, 24) * 1.7
    score += max(0.0, occ - 75) * 0.9
    score += min(boarders, 20) * 1.2
    score += RISK_ORDER.get(delay_risk, 1) * 8
    score += RISK_ORDER.get(readmission_risk, 1) * 4
    if bottleneck != "None":
        score += 10
    if bottleneck in {"Insurance", "Rehab/SNF", "Clinical Stability"}:
        score += 8
    return round(score, 1)


def _prediction_map(model_predictions: pd.DataFrame | list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if model_predictions is None:
        return {}
    if isinstance(model_predictions, pd.DataFrame):
        records = model_predictions.to_dict(orient="records")
    else:
        records = list(model_predictions)
    return {str(item.get("patient_id", "")): item for item in records if item.get("patient_id") is not None}


def _prediction_for_row(
    row: pd.Series | dict[str, Any],
    predictions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    patient_id = str(row.get("patient_id", ""))
    pred = predictions.get(patient_id)
    if pred:
        return {
            "delay_probability": _to_float(pred.get("discharge_delay_risk_probability"), 0.0),
            "delay_risk": str(pred.get("delay_risk_level", "Low")),
            "readmission_probability": _to_float(pred.get("readmission_risk_probability"), 0.0),
            "readmission_risk": str(pred.get("readmission_risk_level", "Low")),
            "delay_hours": max(0.0, _to_float(pred.get("predicted_delay_hours"), 0.0)),
            "prediction_source": str(pred.get("prediction_source", "XGBoost model inference")),
            "model_version": pred.get("model_version"),
            "prediction_timestamp_utc": pred.get("prediction_timestamp_utc"),
        }

    delay_risk = estimate_delay_risk(row)
    readmission_risk = estimate_readmission_risk(row)
    return {
        "delay_probability": RISK_PROBABILITY_FALLBACK[delay_risk],
        "delay_risk": delay_risk,
        "readmission_probability": RISK_PROBABILITY_FALLBACK[readmission_risk],
        "readmission_risk": readmission_risk,
        "delay_hours": estimate_delay_hours_fallback(row),
        "prediction_source": "prospective operational fallback",
        "model_version": None,
        "prediction_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_discharge_queue(
    df: pd.DataFrame,
    model_predictions: pd.DataFrame | list[dict[str, Any]] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Build a model-scored, prioritized multi-patient discharge queue."""
    if df.empty:
        return []

    predictions = _prediction_map(model_predictions)
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        unit = infer_unit(row)
        scored = _prediction_for_row(row, predictions)
        delay_risk = scored["delay_risk"]
        readmission_risk = scored["readmission_risk"]
        delay_hours = round(scored["delay_hours"], 1)
        bottleneck = str(row.get("primary_discharge_bottleneck", "None"))
        status = estimate_case_status(row, delay_risk, readmission_risk)
        score = bed_recovery_score(row, delay_risk, readmission_risk, delay_hours)

        records.append(
            {
                "patient_id": str(row.get("patient_id", "")),
                "unit": unit,
                "age": _to_int(row.get("age", 0)),
                "diagnosis_group": str(row.get("diagnosis_group", "Unknown")),
                "acuity_level": str(row.get("acuity_level", "Unknown")),
                "discharge_destination": str(row.get("discharge_destination", "Unknown")),
                "delay_risk_level": delay_risk,
                "delay_risk_display": _risk_badge(delay_risk),
                "discharge_delay_risk_probability": round(scored["delay_probability"], 4),
                "delay_probability_display": _percentage(scored["delay_probability"]),
                "readmission_risk_level": readmission_risk,
                "readmission_risk_display": _risk_badge(readmission_risk),
                "readmission_risk_probability": round(scored["readmission_probability"], 4),
                "readmission_probability_display": _percentage(scored["readmission_probability"]),
                "predicted_delay_hours": delay_hours,
                # Backward-compatible alias for older dashboard versions.
                "predicted_delay_hours_proxy": delay_hours,
                "primary_bottleneck": bottleneck,
                "owner_role": bottleneck_owner(bottleneck),
                "case_status": status,
                "next_action": bottleneck_next_action(bottleneck),
                "bed_recovery_score": score,
                "current_bed_occupancy_percent": _to_int(row.get("current_bed_occupancy_percent", 0)),
                "ed_boarding_count": _to_int(row.get("ed_boarding_count", 0)),
                "prediction_source": scored["prediction_source"],
                "model_version": scored["model_version"],
                "prediction_timestamp_utc": scored["prediction_timestamp_utc"],
            }
        )

    records.sort(key=lambda item: item["bed_recovery_score"], reverse=True)
    return records[:limit] if limit is not None else records


def build_hospital_capacity_snapshot(
    df: pd.DataFrame,
    model_predictions: pd.DataFrame | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a simulated capacity snapshot using model-scored patient risk."""
    empty_payload = {
        "snapshot_time_utc": datetime.now(timezone.utc).isoformat(),
        "total_beds": sum(UNIT_CAPACITY.values()),
        "occupied_beds": 0,
        "available_beds": sum(UNIT_CAPACITY.values()),
        "occupancy_percent": 0,
        "beds_pending_cleaning": 0,
        "ed_boarders": 0,
        "expected_discharges_today": 0,
        "delayed_discharges": 0,
        "critical_delay_cases": 0,
        "units": [],
        "is_simulated_capacity": True,
        "data_mode": "Simulated/proxy hospital capacity",
    }
    if df.empty:
        return empty_payload

    predictions = _prediction_map(model_predictions)
    working = df.copy()
    working["unit"] = working.apply(infer_unit, axis=1)
    scored_rows = working.apply(lambda row: _prediction_for_row(row, predictions), axis=1)
    working["delay_risk_level"] = [item["delay_risk"] for item in scored_rows]
    working["predicted_delay_hours"] = [item["delay_hours"] for item in scored_rows]
    working["prediction_source"] = [item["prediction_source"] for item in scored_rows]
    working["model_version"] = [item["model_version"] for item in scored_rows]

    units: list[dict[str, Any]] = []
    ed_boarders = (
        int(round(float(working["ed_boarding_count"].quantile(0.75))))
        if "ed_boarding_count" in working
        else 0
    )
    ed_occupied = min(UNIT_CAPACITY["Emergency Department"], max(0, 28 + ed_boarders))
    ed_available = max(0, UNIT_CAPACITY["Emergency Department"] - ed_occupied)
    ed_occ = round((ed_occupied / UNIT_CAPACITY["Emergency Department"]) * 100, 1)
    units.append(
        {
            "unit": "Emergency Department",
            "total_beds": UNIT_CAPACITY["Emergency Department"],
            "occupied_beds": ed_occupied,
            "available_beds": ed_available,
            "occupancy_percent": ed_occ,
            "pending_discharges": 0,
            "delayed_discharges": 0,
            "ed_boarders": ed_boarders,
            "pressure_level": pressure_level_from_occupancy(ed_occ, ed_boarders),
        }
    )

    for unit, bed_count in UNIT_CAPACITY.items():
        if unit == "Emergency Department":
            continue

        group = working[working["unit"] == unit]
        if group.empty:
            occupancy = 70.0
            delayed_rate = 0.0
            expected_ready_rate = 0.0
        else:
            occupancy = round(float(group["current_bed_occupancy_percent"].mean()), 1)
            delayed_rate = float(group["delay_risk_level"].isin(["High", "Critical"]).mean())
            expected_ready_rate = float(
                (
                    (group["predicted_delay_hours"] <= 6)
                    & group["delay_risk_level"].isin(["Low", "Medium"])
                ).mean()
            )

        occupied = min(bed_count, max(0, int(round(bed_count * occupancy / 100))))
        available = max(0, bed_count - occupied)
        pending_discharges = max(0, int(round(occupied * expected_ready_rate * 0.35)))
        delayed_discharges = max(0, int(round(occupied * delayed_rate * 0.25)))
        unit_boarders = max(0, int(round(ed_boarders * (occupied / max(1, sum(UNIT_CAPACITY.values()))))))

        units.append(
            {
                "unit": unit,
                "total_beds": bed_count,
                "occupied_beds": occupied,
                "available_beds": available,
                "occupancy_percent": occupancy,
                "pending_discharges": pending_discharges,
                "delayed_discharges": delayed_discharges,
                "ed_boarders": unit_boarders,
                "pressure_level": pressure_level_from_occupancy(occupancy, unit_boarders),
            }
        )

    total_beds = sum(unit["total_beds"] for unit in units)
    occupied_beds = sum(unit["occupied_beds"] for unit in units)
    available_beds = sum(unit["available_beds"] for unit in units)
    expected_discharges = sum(unit["pending_discharges"] for unit in units)
    delayed_discharges = sum(unit["delayed_discharges"] for unit in units)
    critical_delay_cases = int((working["delay_risk_level"] == "Critical").sum())
    beds_pending_cleaning = max(1, min(12, int(round(expected_discharges * 0.25))))
    model_versions = [str(v) for v in working["model_version"].dropna().unique().tolist() if str(v)]
    sources = working["prediction_source"].dropna().unique().tolist()

    return {
        "snapshot_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "available_beds": available_beds,
        "occupancy_percent": round((occupied_beds / total_beds) * 100, 1) if total_beds else 0,
        "beds_pending_cleaning": beds_pending_cleaning,
        "ed_boarders": ed_boarders,
        "expected_discharges_today": expected_discharges,
        "delayed_discharges": delayed_discharges,
        "critical_delay_cases": critical_delay_cases,
        "units": units,
        "is_simulated_capacity": True,
        "data_mode": "Simulated/proxy capacity with cached patient-level model scoring",
        "prediction_source": ", ".join(str(source) for source in sources),
        "model_version": model_versions[0] if len(model_versions) == 1 else model_versions,
    }
