"""Department- and sidebar-responsive packing queue.

The Top 5 queue should not behave like a static demo table.  This module uses the
same local pipeline as the single-item decision path, then applies a lightweight
expert-system pressure layer so department, sliders, hour/day, and season visibly
change the queue while staying zero-token and fully local.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.model import load_model_and_predict
from backend.shortage_rules import calculate_shortage_risk
from backend.usable_stock import build_usable_stock_analysis
from backend.packing_optimizer import calculate_priority_and_pack_quantity


DEFAULTS: Dict[str, Any] = {
    "day_of_week": 0,
    "hour": 12,
    "season": "Summer",
    "reorder_point": 25,
    "unit_cost": 15.0,
    "supplier_reliability_score": 0.9,
    "pack_time_minutes": 4.5,
    "clinical_criticality": 3,
    "patient_volume": 10,
    "acuity_level": 2.0,
    "procedure_count": 4,
    "recent_usage_rate": 5.0,
    "supplier_delay_days": 2.0,
}

# How strongly each supply category responds to the operational sliders.
CATEGORY_SENSITIVITY: Dict[str, Dict[str, float]] = {
    "Respiratory": {"volume": 0.70, "acuity": 1.25, "procedures": 0.35, "winter": 0.45, "summer": -0.05},
    "PPE": {"volume": 1.10, "acuity": 0.45, "procedures": 0.40, "winter": 0.25, "summer": 0.05},
    "IV Supplies": {"volume": 0.80, "acuity": 0.80, "procedures": 0.65, "winter": 0.05, "summer": 0.20},
    "Wound Care": {"volume": 0.45, "acuity": 0.40, "procedures": 0.60, "winter": 0.00, "summer": 0.05},
    "Catheterization": {"volume": 0.35, "acuity": 0.80, "procedures": 0.85, "winter": 0.05, "summer": 0.00},
    "Lab Supplies": {"volume": 0.55, "acuity": 0.55, "procedures": 0.75, "winter": 0.05, "summer": 0.00},
    "Surgical Supplies": {"volume": 0.30, "acuity": 0.65, "procedures": 1.30, "winter": 0.00, "summer": 0.00},
    "Monitoring": {"volume": 0.30, "acuity": 1.10, "procedures": 0.25, "winter": 0.05, "summer": 0.00},
}

# Department context nudges specific categories upward so ICU, ED, Surgery, etc.
# do not all produce the same queue.
DEPARTMENT_CATEGORY_BONUS: Dict[str, Dict[str, float]] = {
    "Emergency Department": {"IV Supplies": 0.22, "PPE": 0.20, "Wound Care": 0.25, "Respiratory": 0.18, "Lab Supplies": 0.10},
    "ICU": {"Respiratory": 0.35, "Monitoring": 0.25, "IV Supplies": 0.22, "Catheterization": 0.20, "PPE": 0.10},
    "Surgery": {"Surgical Supplies": 0.45, "PPE": 0.20, "IV Supplies": 0.15, "Wound Care": 0.15},
    "Med-Surg": {"IV Supplies": 0.18, "Wound Care": 0.18, "PPE": 0.12, "Catheterization": 0.10},
    "Labor and Delivery": {"IV Supplies": 0.20, "PPE": 0.15, "Surgical Supplies": 0.12, "Wound Care": 0.10},
    "Radiology": {"IV Supplies": 0.15, "Monitoring": 0.15, "PPE": 0.10},
    "Outpatient Clinic": {"PPE": 0.18, "Lab Supplies": 0.15, "Wound Care": 0.12},
}


def _as_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clean_scenario(scenario: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Normalize frontend/sidebar inputs into safe numeric values."""
    scenario = dict(scenario or {})
    cleaned: Dict[str, Any] = {}

    for key, default in DEFAULTS.items():
        if isinstance(default, int):
            cleaned[key] = _as_int(scenario.get(key), default)
        elif isinstance(default, float):
            cleaned[key] = _as_float(scenario.get(key), default)
        else:
            cleaned[key] = scenario.get(key, default) or default

    if "current_stock" in scenario:
        cleaned["current_stock"] = _as_int(scenario.get("current_stock"), 30)
    if "department" in scenario and scenario.get("department"):
        cleaned["department"] = str(scenario.get("department"))
    if "agent_mode" in scenario and scenario.get("agent_mode"):
        cleaned["agent_mode"] = str(scenario.get("agent_mode"))
    return cleaned


def _scenario_pressure_multiplier(telemetry: Mapping[str, Any], scenario: Mapping[str, Any]) -> tuple[float, str]:
    """Return an expert-system demand multiplier and a short reason.

    This is deliberately simple and explainable. It does not call an LLM.
    """
    category = str(telemetry.get("item_category", ""))
    department = str(telemetry.get("department", scenario.get("department", "")))
    season = str(scenario.get("season", telemetry.get("season", "Summer")))
    hour = _as_int(scenario.get("hour", telemetry.get("hour", 12)), 12)
    day_of_week = _as_int(scenario.get("day_of_week", telemetry.get("day_of_week", 0)), 0)

    profile = CATEGORY_SENSITIVITY.get(category, {})
    multiplier = 1.0

    # Normalize sliders around the original default/demo center so movement up/down matters.
    volume_delta = (_as_float(scenario.get("patient_volume"), 10.0) - 15.0) / 85.0
    acuity_delta = (_as_float(scenario.get("acuity_level"), 2.0) - 2.5) / 1.5
    procedure_delta = (_as_float(scenario.get("procedure_count"), 4.0) - 6.0) / 44.0
    usage_delta = (_as_float(scenario.get("recent_usage_rate"), 5.0) - 8.5) / 41.5
    delay_delta = (_as_float(scenario.get("supplier_delay_days"), 2.0) - 2.5) / 11.5

    multiplier += volume_delta * profile.get("volume", 0.45)
    multiplier += acuity_delta * profile.get("acuity", 0.50)
    multiplier += procedure_delta * profile.get("procedures", 0.45)
    multiplier += usage_delta * 0.35
    multiplier += delay_delta * 0.18

    if season == "Winter":
        multiplier += profile.get("winter", 0.02)
    elif season == "Summer":
        multiplier += profile.get("summer", 0.02)
    elif season == "Autumn":
        multiplier += 0.03 if category in {"Respiratory", "PPE"} else 0.0
    elif season == "Spring":
        multiplier += 0.02 if category in {"PPE", "Respiratory"} else 0.0

    multiplier += DEPARTMENT_CATEGORY_BONUS.get(department, {}).get(category, 0.0)

    # Time/day pressure: late-night ED/ICU and weekday surgery/procedures need more attention.
    if department in {"Emergency Department", "ICU"} and (hour >= 18 or hour <= 6):
        multiplier += 0.08
    if department == "Surgery" and 6 <= hour <= 15 and day_of_week in {0, 1, 2, 3, 4}:
        multiplier += 0.10
    if day_of_week in {5, 6} and department in {"Emergency Department", "ICU"}:
        multiplier += 0.05

    # Keep the expert layer bounded so the ML model still matters.
    multiplier = max(0.35, min(2.60, multiplier))
    note = f"{department}/{category} pressure x{multiplier:.2f} from sliders, season, hour, and department context"
    return multiplier, note


def _apply_sidebar_scenario(record: Mapping[str, Any], scenario: Mapping[str, Any]) -> Dict[str, Any]:
    """Blend a stored inventory record with active sidebar controls."""
    telemetry = dict(record)
    for key, value in DEFAULTS.items():
        telemetry.setdefault(key, value)

    # Sidebar controls represent the current operating scenario. They should affect
    # every candidate row in the Top 5 queue.
    for key in [
        "patient_volume",
        "acuity_level",
        "procedure_count",
        "recent_usage_rate",
        "supplier_delay_days",
        "day_of_week",
        "hour",
        "season",
        "reorder_point",
        "supplier_reliability_score",
        "pack_time_minutes",
        "clinical_criticality",
        "agent_mode",
    ]:
        if key in scenario:
            telemetry[key] = scenario[key]

    # Current Stock is a scenario pressure slider. Use it to scale each item from its
    # stored baseline rather than making every supply have the exact same stock.
    if "current_stock" in scenario:
        baseline_stock = _as_float(record.get("current_stock"), 30.0)
        scenario_stock = _as_float(scenario.get("current_stock"), 30.0)
        stock_scale = max(0.05, min(3.0, scenario_stock / 30.0))
        telemetry["current_stock"] = int(round(baseline_stock * stock_scale))

    return telemetry


def build_packing_queue(
    inventory_records: Iterable[Mapping[str, Any]],
    limit: int = 5,
    max_records: int = 50,
    scenario: Optional[Mapping[str, Any]] = None,
    transfer_inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Return a sorted, sidebar-responsive packing queue.

    Stage 2 upgrade: each row is now scored against usable stock instead of
    raw total stock. Expired/recalled units and active task reservations are
    removed before shortage risk is calculated. Transfer candidates from other
    departments are also surfaced.
    """
    scenario_clean = _clean_scenario(scenario)
    scored_records: List[Dict[str, Any]] = []
    all_records = list(inventory_records)
    all_transfer_records = list(transfer_inventory_records) if transfer_inventory_records is not None else all_records

    for rec in all_records[:max_records]:
        telemetry = _apply_sidebar_scenario(rec, scenario_clean)
        multiplier, pressure_note = _scenario_pressure_multiplier(telemetry, scenario_clean)

        predicted = load_model_and_predict(telemetry) * multiplier
        usable_analysis = build_usable_stock_analysis(
            telemetry,
            predicted_24h_demand=predicted,
            inventory_records=all_transfer_records,
        )
        shortage = usable_analysis.get("shortage_risk_using_usable_stock", {})
        priority = calculate_priority_and_pack_quantity(
            telemetry.get("item_name", "Unknown Item"),
            telemetry.get("department", "Unknown Department"),
            shortage,
            telemetry,
        )

        scored_records.append({
            "item_name": telemetry.get("item_name", "Unknown Item"),
            "department": telemetry.get("department", "Unknown Department"),
            "item_category": telemetry.get("item_category", "Unknown"),
            "stock_basis": "usable_stock",
            "total_stock": usable_analysis.get("total_stock", telemetry.get("current_stock", 0)),
            "current_stock": shortage.get("current_stock", usable_analysis.get("usable_stock", 0)),
            "usable_stock": usable_analysis.get("usable_stock", 0),
            "unsafe_stock": usable_analysis.get("unsafe_stock", 0),
            "expired_stock": usable_analysis.get("expired_stock", 0),
            "recalled_stock": usable_analysis.get("recalled_stock", 0),
            "active_task_reserved_stock": usable_analysis.get("active_task_reserved_stock", 0),
            "wrong_location_stock": usable_analysis.get("wrong_location_stock", 0),
            "transfer_candidate_stock": usable_analysis.get("transfer_candidate_stock", 0),
            "effective_stock_after_transfer": usable_analysis.get("effective_stock_after_transfer", 0),
            "predicted_24h_demand": round(shortage.get("predicted_24h_demand", predicted), 2),
            "shortage_gap": round(shortage.get("shortage_gap", 0), 2),
            "true_shortage_gap": usable_analysis.get("true_shortage_gap", shortage.get("shortage_gap", 0)),
            "post_transfer_gap": usable_analysis.get("post_transfer_gap", shortage.get("shortage_gap", 0)),
            "coverage_ratio": round(shortage.get("coverage_ratio", 0), 3),
            "risk_level": shortage.get("risk_level", "Low"),
            "recommended_pack_quantity": priority["recommended_pack_quantity"],
            "priority_score": priority["priority_score"],
            "escalation_required": "Yes" if priority["escalation_required"] else "No",
            "recommended_action": priority["recommended_action"],
            "stage2_action": usable_analysis.get("recommended_stage2_action", ""),
            "scenario_pressure_score": round(multiplier, 2),
            "pressure_note": pressure_note,
        })

    risk_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    scored_records.sort(
        key=lambda row: (
            risk_rank.get(row["risk_level"], 0),
            row["priority_score"],
            row["true_shortage_gap"],
            row["scenario_pressure_score"],
        ),
        reverse=True,
    )
    return scored_records[:limit]
