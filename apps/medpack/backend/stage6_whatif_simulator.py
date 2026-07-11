"""Stage 6 what-if surge simulator for MedPack AI.

This module stress-tests the selected supply scenario by applying an operational
shock such as ED surge, ICU respiratory spike, supplier delay, mass-casualty
mode, or weekend staffing pressure.  The adjusted telemetry is then pushed
through the existing Stage 2-5 stack so the simulator shows forecast impact,
true usable-stock gap, transfer/supplier/substitute response, ROI impact, and
the final command-center priority.

Everything here is deterministic/local.  It does not call Groq/Gemini, does not
stream, and does not write memory events, so it is safe for the demo.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.traceability import ensure_traceability_fields, load_inventory_state
from backend.task_manager import list_tasks
from backend.stage3_action_plan import build_stage3_action_plan
from backend.stage4_roi import build_stage4_roi_analysis
from backend.stage5_command_center import build_stage5_command_center

SCENARIO_PATH = "database/scenario_playbooks.json"

DEFAULT_SCENARIOS: Dict[str, Any] = {
    "stage": "Stage 6 - What-If Surge Simulator",
    "description": (
        "Demo scenario playbooks. Each scenario modifies the selected telemetry "
        "then runs the adjusted case through Stages 2-5."
    ),
    "scenarios": [
        {
            "scenario_id": "ED_SURGE_40",
            "scenario_name": "ED Surge +40%",
            "severity": "High",
            "affected_departments": ["Emergency Department"],
            "affected_categories": ["IV Supplies", "PPE", "Respiratory", "Lab Supplies"],
            "spillover_factor": 0.35,
            "modifiers": {
                "multipliers": {
                    "patient_volume": 1.40,
                    "recent_usage_rate": 1.35,
                    "procedure_count": 1.20
                },
                "adders": {
                    "acuity_level": 0.25,
                    "supplier_delay_days": 0.50
                },
                "set_fields": {
                    "scenario_tag": "ED surge"
                }
            },
            "recommended_play": "Pre-pack ED IV/PPE/respiratory supplies and check transfer candidates before the surge window peaks."
        },
        {
            "scenario_id": "ICU_RESPIRATORY_SPIKE",
            "scenario_name": "ICU Respiratory Spike",
            "severity": "High",
            "affected_departments": ["ICU"],
            "affected_categories": ["Respiratory", "Monitoring", "IV Supplies"],
            "spillover_factor": 0.25,
            "modifiers": {
                "multipliers": {
                    "patient_volume": 1.25,
                    "recent_usage_rate": 1.60,
                    "procedure_count": 1.25
                },
                "adders": {
                    "acuity_level": 0.60,
                    "supplier_delay_days": 0.75
                },
                "set_fields": {
                    "scenario_tag": "ICU respiratory spike"
                }
            },
            "recommended_play": "Move respiratory inventory closer to ICU, validate oxygen-delivery substitutes, and escalate supplier timing for critical items."
        },
        {
            "scenario_id": "FLU_SEASON_DEMAND",
            "scenario_name": "Flu Season Demand",
            "severity": "Medium",
            "affected_departments": [],
            "affected_categories": ["PPE", "Respiratory", "IV Supplies"],
            "spillover_factor": 1.0,
            "modifiers": {
                "multipliers": {
                    "patient_volume": 1.15,
                    "recent_usage_rate": 1.30,
                    "procedure_count": 1.10
                },
                "adders": {
                    "supplier_delay_days": 0.50
                },
                "set_fields": {
                    "season": "Winter",
                    "scenario_tag": "flu season"
                }
            },
            "recommended_play": "Raise PAR levels for PPE/respiratory lines, watch expirations, and avoid emergency-buying by using planned replenishment."
        },
        {
            "scenario_id": "SUPPLIER_DELAY_5D",
            "scenario_name": "Supplier Delay +5 Days",
            "severity": "Medium",
            "affected_departments": [],
            "affected_categories": [],
            "spillover_factor": 1.0,
            "modifiers": {
                "multipliers": {
                    "supplier_reliability_score": 0.85
                },
                "adders": {
                    "supplier_delay_days": 5.00
                },
                "set_fields": {
                    "scenario_tag": "supplier delay"
                }
            },
            "recommended_play": "Do not wait on the primary vendor for short-window shortages; evaluate internal transfer and backup/emergency vendors."
        },
        {
            "scenario_id": "MASS_CASUALTY_MODE",
            "scenario_name": "Mass Casualty Mode",
            "severity": "Critical",
            "affected_departments": ["Emergency Department", "ICU", "Surgery"],
            "affected_categories": [],
            "spillover_factor": 0.55,
            "modifiers": {
                "multipliers": {
                    "patient_volume": 2.00,
                    "recent_usage_rate": 1.75,
                    "procedure_count": 1.60,
                    "pack_time_minutes": 1.20
                },
                "adders": {
                    "acuity_level": 1.00,
                    "supplier_delay_days": 1.00,
                    "clinical_criticality": 1
                },
                "stock_reduction_pct": 0.10,
                "set_fields": {
                    "scenario_tag": "mass casualty"
                }
            },
            "recommended_play": "Switch to command mode: pre-stage critical supplies, trigger transfer plan, rush-order residual gaps, and escalate unresolved P0/P1 items."
        },
        {
            "scenario_id": "WEEKEND_STAFFING_CONSTRAINT",
            "scenario_name": "Weekend Staffing Constraint",
            "severity": "Medium",
            "affected_departments": [],
            "affected_categories": [],
            "spillover_factor": 1.0,
            "modifiers": {
                "multipliers": {
                    "pack_time_minutes": 1.45,
                    "recent_usage_rate": 1.10
                },
                "adders": {
                    "supplier_delay_days": 1.00
                },
                "set_fields": {
                    "scenario_tag": "weekend staffing"
                }
            },
            "recommended_play": "Start packing earlier, reduce avoidable transfers, and escalate tasks with short response windows."
        },
        {
            "scenario_id": "SURGERY_SCHEDULE_SPIKE",
            "scenario_name": "Surgery Schedule Spike",
            "severity": "High",
            "affected_departments": ["Surgery"],
            "affected_categories": ["Surgical Supplies", "IV Supplies", "Catheterization", "Wound Care"],
            "spillover_factor": 0.20,
            "modifiers": {
                "multipliers": {
                    "procedure_count": 1.80,
                    "recent_usage_rate": 1.35,
                    "patient_volume": 1.20
                },
                "adders": {
                    "acuity_level": 0.20
                },
                "set_fields": {
                    "scenario_tag": "surgery schedule spike"
                }
            },
            "recommended_play": "Pre-stage procedure-linked supplies and avoid pulling transfer stock from Surgery if it creates a secondary shortage."
        }
    ],
    "custom_modifier_schema": {
        "demand_multiplier": "Multiplies patient_volume, recent_usage_rate, and procedure_count.",
        "supplier_delay_add_days": "Adds days to supplier_delay_days.",
        "stock_reduction_units": "Subtracts units from current_stock.",
        "stock_reduction_pct": "Subtracts percent of current_stock; use 0.10 for 10%.",
        "acuity_delta": "Adds to acuity_level, capped at 4.0.",
        "pack_time_multiplier": "Multiplies pack_time_minutes."
    }
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    return int(round(_as_float(value, float(default))))


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def load_stage6_scenarios() -> Dict[str, Any]:
    """Load editable scenario playbooks."""
    if not os.path.exists(SCENARIO_PATH):
        return deepcopy(DEFAULT_SCENARIOS)
    try:
        with open(SCENARIO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            merged = deepcopy(DEFAULT_SCENARIOS)
            # Shallow merge while preserving the default schema if an edited file is partial.
            for k, v in data.items():
                merged[k] = v
            if not merged.get("scenarios"):
                merged["scenarios"] = deepcopy(DEFAULT_SCENARIOS["scenarios"])
            return merged
    except Exception:
        pass
    return deepcopy(DEFAULT_SCENARIOS)


def get_scenario(scenario_id: str) -> Dict[str, Any]:
    playbooks = load_stage6_scenarios()
    for scenario in playbooks.get("scenarios", []):
        if str(scenario.get("scenario_id")) == str(scenario_id):
            return dict(scenario)
    return dict(playbooks.get("scenarios", [DEFAULT_SCENARIOS["scenarios"][0]])[0])


def _scenario_applicability_factor(telemetry: Mapping[str, Any], scenario: Mapping[str, Any]) -> float:
    """Return 1.0 for a direct hit, a spillover value for related cases."""
    dept = _norm(telemetry.get("department"))
    category = _norm(telemetry.get("item_category"))
    affected_depts = [_norm(x) for x in scenario.get("affected_departments", []) or []]
    affected_cats = [_norm(x) for x in scenario.get("affected_categories", []) or []]

    # Empty affected lists mean the scenario is global.
    if not affected_depts and not affected_cats:
        return 1.0
    if affected_depts and dept in affected_depts:
        return 1.0
    if affected_cats and category in affected_cats:
        return 1.0
    return _as_float(scenario.get("spillover_factor"), 0.25)


def _apply_scaled_multiplier(original: float, multiplier: float, factor: float) -> float:
    scaled_multiplier = 1.0 + ((multiplier - 1.0) * factor)
    return original * scaled_multiplier


def apply_scenario_to_telemetry(
    telemetry: Mapping[str, Any],
    scenario: Mapping[str, Any],
    custom_modifiers: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return adjusted telemetry plus an applied-modifier audit trail."""
    baseline = dict(telemetry or {})
    adjusted = dict(baseline)
    factor = _scenario_applicability_factor(baseline, scenario)
    mods = scenario.get("modifiers", {}) or {}
    applied: List[Dict[str, Any]] = []

    for field, multiplier in (mods.get("multipliers", {}) or {}).items():
        before = _as_float(adjusted.get(field), 0.0)
        after = _apply_scaled_multiplier(before, _as_float(multiplier, 1.0), factor)
        adjusted[field] = round(after, 3)
        applied.append({"field": field, "operation": "multiply", "requested": multiplier, "factor": round(factor, 2), "before": before, "after": adjusted[field]})

    for field, adder in (mods.get("adders", {}) or {}).items():
        before = _as_float(adjusted.get(field), 0.0)
        after = before + (_as_float(adder, 0.0) * factor)
        adjusted[field] = round(after, 3)
        applied.append({"field": field, "operation": "add", "requested": adder, "factor": round(factor, 2), "before": before, "after": adjusted[field]})

    stock_reduction_pct = _as_float(mods.get("stock_reduction_pct"), 0.0) * factor
    if stock_reduction_pct > 0:
        before = _as_float(adjusted.get("current_stock"), 0.0)
        after = max(0.0, before - (before * stock_reduction_pct))
        adjusted["current_stock"] = round(after, 3)
        applied.append({"field": "current_stock", "operation": "reduce_pct", "requested": mods.get("stock_reduction_pct"), "factor": round(factor, 2), "before": before, "after": adjusted["current_stock"]})

    for field, value in (mods.get("set_fields", {}) or {}).items():
        before = adjusted.get(field)
        adjusted[field] = value
        applied.append({"field": field, "operation": "set", "requested": value, "factor": round(factor, 2), "before": before, "after": adjusted[field]})

    custom = dict(custom_modifiers or {})
    if custom:
        demand_multiplier = _as_float(custom.get("demand_multiplier"), 1.0)
        if demand_multiplier != 1.0:
            for field in ("patient_volume", "recent_usage_rate", "procedure_count"):
                before = _as_float(adjusted.get(field), 0.0)
                adjusted[field] = round(before * demand_multiplier, 3)
                applied.append({"field": field, "operation": "custom_demand_multiplier", "requested": demand_multiplier, "factor": 1.0, "before": before, "after": adjusted[field]})
        delay_add = _as_float(custom.get("supplier_delay_add_days"), 0.0)
        if delay_add:
            before = _as_float(adjusted.get("supplier_delay_days"), 0.0)
            adjusted["supplier_delay_days"] = round(before + delay_add, 3)
            applied.append({"field": "supplier_delay_days", "operation": "custom_add", "requested": delay_add, "factor": 1.0, "before": before, "after": adjusted["supplier_delay_days"]})
        acuity_delta = _as_float(custom.get("acuity_delta"), 0.0)
        if acuity_delta:
            before = _as_float(adjusted.get("acuity_level"), 0.0)
            adjusted["acuity_level"] = round(before + acuity_delta, 3)
            applied.append({"field": "acuity_level", "operation": "custom_add", "requested": acuity_delta, "factor": 1.0, "before": before, "after": adjusted["acuity_level"]})
        pack_mult = _as_float(custom.get("pack_time_multiplier"), 1.0)
        if pack_mult != 1.0:
            before = _as_float(adjusted.get("pack_time_minutes"), 0.0)
            adjusted["pack_time_minutes"] = round(before * pack_mult, 3)
            applied.append({"field": "pack_time_minutes", "operation": "custom_multiply", "requested": pack_mult, "factor": 1.0, "before": before, "after": adjusted["pack_time_minutes"]})
        stock_reduction_units = _as_float(custom.get("stock_reduction_units"), 0.0)
        if stock_reduction_units:
            before = _as_float(adjusted.get("current_stock"), 0.0)
            adjusted["current_stock"] = round(max(0.0, before - stock_reduction_units), 3)
            applied.append({"field": "current_stock", "operation": "custom_reduce_units", "requested": stock_reduction_units, "factor": 1.0, "before": before, "after": adjusted["current_stock"]})
        custom_stock_pct = _as_float(custom.get("stock_reduction_pct"), 0.0)
        if custom_stock_pct:
            before = _as_float(adjusted.get("current_stock"), 0.0)
            adjusted["current_stock"] = round(max(0.0, before - (before * custom_stock_pct)), 3)
            applied.append({"field": "current_stock", "operation": "custom_reduce_pct", "requested": custom_stock_pct, "factor": 1.0, "before": before, "after": adjusted["current_stock"]})

    # Sensible caps for the demo controls.
    adjusted["patient_volume"] = int(round(_clip(_as_float(adjusted.get("patient_volume"), 1.0), 1.0, 250.0)))
    adjusted["procedure_count"] = int(round(_clip(_as_float(adjusted.get("procedure_count"), 0.0), 0.0, 30.0)))
    adjusted["acuity_level"] = round(_clip(_as_float(adjusted.get("acuity_level"), 1.0), 1.0, 4.0), 2)
    adjusted["clinical_criticality"] = int(round(_clip(_as_float(adjusted.get("clinical_criticality"), 1.0), 1.0, 4.0)))
    adjusted["current_stock"] = int(round(_clip(_as_float(adjusted.get("current_stock"), 0.0), 0.0, 1000.0)))
    adjusted["recent_usage_rate"] = round(_clip(_as_float(adjusted.get("recent_usage_rate"), 0.0), 0.0, 500.0), 2)
    adjusted["supplier_delay_days"] = round(_clip(_as_float(adjusted.get("supplier_delay_days"), 0.0), 0.0, 30.0), 2)
    adjusted["pack_time_minutes"] = round(_clip(_as_float(adjusted.get("pack_time_minutes"), 1.0), 0.1, 120.0), 2)
    adjusted["scenario_id"] = scenario.get("scenario_id")
    adjusted["scenario_name"] = scenario.get("scenario_name")

    return {
        "baseline_telemetry": baseline,
        "scenario_telemetry": adjusted,
        "applicability_factor": round(factor, 2),
        "applied_modifiers": applied,
    }


def fast_scenario_forecast(telemetry: Mapping[str, Any]) -> float:
    """Deterministic 24h forecast used by the no-freeze simulator."""
    recent_usage = _as_float(telemetry.get("recent_usage_rate"), 5.0)
    volume = _as_float(telemetry.get("patient_volume"), 10.0)
    acuity = _as_float(telemetry.get("acuity_level"), 2.0)
    procedures = _as_float(telemetry.get("procedure_count"), 4.0)
    delay = _as_float(telemetry.get("supplier_delay_days"), 2.0)
    criticality = _as_float(telemetry.get("clinical_criticality"), 2.0)

    pred = (recent_usage * 0.8) + (volume * acuity * 0.15) + (procedures * 0.5)
    if delay > 4.0:
        pred += 2.0 + min(delay - 4.0, 8.0) * 0.25
    if criticality >= 4:
        pred += 1.0
    return round(max(0.0, float(pred)), 2)


def _run_stage_stack(
    telemetry: Mapping[str, Any],
    predicted_24h_demand: Optional[float] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    predicted = fast_scenario_forecast(telemetry) if predicted_24h_demand is None else round(_as_float(predicted_24h_demand), 2)
    records = [dict(r) for r in (inventory_records if inventory_records is not None else (ensure_traceability_fields() or load_inventory_state(enrich=True)))]
    task_rows = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]

    stage3 = build_stage3_action_plan(
        telemetry,
        predicted_24h_demand=predicted,
        inventory_records=records,
        tasks=task_rows,
    )
    stage4 = build_stage4_roi_analysis(
        telemetry,
        predicted_24h_demand=predicted,
        inventory_records=records,
        tasks=task_rows,
        stage3_plan=stage3,
    )
    stage5 = build_stage5_command_center(
        telemetry,
        predicted_24h_demand=predicted,
        inventory_records=records,
        tasks=task_rows,
        stage3_plan=stage3,
        stage4_roi=stage4,
    )
    return {
        "predicted_24h_demand": predicted,
        "stage3_action_plan": stage3,
        "stage4_roi_analysis": stage4,
        "stage5_command_center": stage5,
    }


def _priority_rank(priority_code: Any) -> int:
    return {"P0": 4, "P1": 3, "P2": 2, "P3": 1}.get(str(priority_code or "P3").upper(), 1)


def build_stage6_whatif_simulation(
    telemetry: Mapping[str, Any],
    scenario_id: str = "ED_SURGE_40",
    custom_modifiers: Optional[Mapping[str, Any]] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run one scenario against the selected item/department."""
    base = dict(telemetry or {})
    scenario = get_scenario(scenario_id)
    applied = apply_scenario_to_telemetry(base, scenario, custom_modifiers=custom_modifiers)

    records = [dict(r) for r in (inventory_records if inventory_records is not None else (ensure_traceability_fields() or load_inventory_state(enrich=True)))]
    task_rows = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]

    baseline_stack = _run_stage_stack(base, inventory_records=records, tasks=task_rows)
    scenario_stack = _run_stage_stack(applied["scenario_telemetry"], inventory_records=records, tasks=task_rows)

    baseline_stage5 = baseline_stack["stage5_command_center"]
    scenario_stage5 = scenario_stack["stage5_command_center"]
    baseline_stage3 = baseline_stack["stage3_action_plan"]
    scenario_stage3 = scenario_stack["stage3_action_plan"]
    baseline_stage4 = baseline_stack["stage4_roi_analysis"]
    scenario_stage4 = scenario_stack["stage4_roi_analysis"]

    demand_delta = round(scenario_stack["predicted_24h_demand"] - baseline_stack["predicted_24h_demand"], 2)
    gap_delta = round(_as_float(scenario_stage5.get("true_shortage_gap"), 0.0) - _as_float(baseline_stage5.get("true_shortage_gap"), 0.0), 2)
    net_value_delta = round(_as_float(scenario_stage5.get("net_value_estimate"), 0.0) - _as_float(baseline_stage5.get("net_value_estimate"), 0.0), 2)
    priority_delta = _priority_rank(scenario_stage5.get("priority_code")) - _priority_rank(baseline_stage5.get("priority_code"))

    scenario_score = (
        max(0.0, _as_float(scenario_stage5.get("true_shortage_gap"), 0.0)) * 2.0
        + max(0.0, demand_delta)
        + max(0, priority_delta) * 10.0
        + max(0.0, _as_float(scenario_stage5.get("open_action_count"), 0.0)) * 1.5
    )

    if _as_float(scenario_stage5.get("true_shortage_gap"), 0.0) <= 0:
        recommended = f"{scenario.get('scenario_name')} does not create a true shortage for this item. Keep monitor mode and re-check the next forecast refresh."
    elif priority_delta > 0:
        recommended = (
            f"{scenario.get('scenario_name')} worsens command priority from {baseline_stage5.get('priority_code')} "
            f"to {scenario_stage5.get('priority_code')}. Execute the Stage 5 action cards and use the Stage 3 transfer/supplier path immediately."
        )
    else:
        recommended = (
            f"{scenario.get('scenario_name')} creates or preserves a true gap of {scenario_stage5.get('true_shortage_gap')} units. "
            f"Use the Stage 5 commander decision: {scenario_stage5.get('commander_decision')}"
        )

    summary = (
        f"What-if result for {scenario.get('scenario_name')}: demand changes from "
        f"{baseline_stack['predicted_24h_demand']} to {scenario_stack['predicted_24h_demand']} units "
        f"({demand_delta:+.1f}). True gap changes from {baseline_stage5.get('true_shortage_gap')} "
        f"to {scenario_stage5.get('true_shortage_gap')} units ({gap_delta:+.1f}). "
        f"Priority moves {baseline_stage5.get('priority_code')} → {scenario_stage5.get('priority_code')}."
    )

    return {
        "stage": "Stage 6 - What-If Surge Simulator",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scenario": {
            "scenario_id": scenario.get("scenario_id"),
            "scenario_name": scenario.get("scenario_name"),
            "severity": scenario.get("severity"),
            "recommended_play": scenario.get("recommended_play"),
            "applicability_factor": applied.get("applicability_factor"),
        },
        "item_name": base.get("item_name"),
        "department": base.get("department"),
        "baseline_forecast": baseline_stack["predicted_24h_demand"],
        "scenario_forecast": scenario_stack["predicted_24h_demand"],
        "demand_delta": demand_delta,
        "baseline_true_shortage_gap": baseline_stage5.get("true_shortage_gap", 0),
        "scenario_true_shortage_gap": scenario_stage5.get("true_shortage_gap", 0),
        "true_shortage_gap_delta": gap_delta,
        "baseline_priority_code": baseline_stage5.get("priority_code"),
        "scenario_priority_code": scenario_stage5.get("priority_code"),
        "priority_delta": priority_delta,
        "baseline_command_status": baseline_stage5.get("command_status"),
        "scenario_command_status": scenario_stage5.get("command_status"),
        "baseline_net_value": baseline_stage5.get("net_value_estimate", 0),
        "scenario_net_value": scenario_stage5.get("net_value_estimate", 0),
        "net_value_delta": net_value_delta,
        "scenario_score": round(scenario_score, 2),
        "simulator_summary": summary,
        "recommended_scenario_action": recommended,
        "applied_modifiers": applied.get("applied_modifiers", []),
        "baseline_telemetry": applied.get("baseline_telemetry", {}),
        "scenario_telemetry": applied.get("scenario_telemetry", {}),
        "baseline_stage3_action_plan": baseline_stage3,
        "scenario_stage3_action_plan": scenario_stage3,
        "baseline_stage4_roi_analysis": baseline_stage4,
        "scenario_stage4_roi_analysis": scenario_stage4,
        "baseline_stage5_command_center": baseline_stage5,
        "scenario_stage5_command_center": scenario_stage5,
        "control_tower_summary": (
            f"Stage 6 simulator: {summary} Recommended action: {recommended}"
        ),
    }


def build_stage6_scenario_benchmark(
    telemetry: Mapping[str, Any],
    custom_modifiers: Optional[Mapping[str, Any]] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run every predefined scenario and return a sorted benchmark table."""
    playbooks = load_stage6_scenarios()
    rows = []
    details = {}
    records = [dict(r) for r in (inventory_records if inventory_records is not None else (ensure_traceability_fields() or load_inventory_state(enrich=True)))]
    task_rows = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]

    for scenario in playbooks.get("scenarios", []):
        sim = build_stage6_whatif_simulation(
            telemetry,
            scenario_id=scenario.get("scenario_id"),
            custom_modifiers=custom_modifiers,
            inventory_records=records,
            tasks=task_rows,
        )
        rows.append({
            "scenario_id": sim["scenario"]["scenario_id"],
            "scenario_name": sim["scenario"]["scenario_name"],
            "severity": sim["scenario"].get("severity"),
            "baseline_forecast": sim.get("baseline_forecast"),
            "scenario_forecast": sim.get("scenario_forecast"),
            "demand_delta": sim.get("demand_delta"),
            "baseline_gap": sim.get("baseline_true_shortage_gap"),
            "scenario_gap": sim.get("scenario_true_shortage_gap"),
            "gap_delta": sim.get("true_shortage_gap_delta"),
            "baseline_priority": sim.get("baseline_priority_code"),
            "scenario_priority": sim.get("scenario_priority_code"),
            "scenario_score": sim.get("scenario_score"),
            "recommended_action": sim.get("recommended_scenario_action"),
        })
        details[scenario.get("scenario_id")] = sim

    rows.sort(key=lambda r: (_priority_rank(r.get("scenario_priority")), _as_float(r.get("scenario_score"), 0.0)), reverse=True)
    top = rows[0] if rows else {}
    return {
        "stage": "Stage 6 - What-If Surge Simulator Benchmark",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "item_name": (telemetry or {}).get("item_name"),
        "department": (telemetry or {}).get("department"),
        "scenario_count": len(rows),
        "highest_risk_scenario": top,
        "benchmark_rows": rows,
        "scenario_details": details,
        "control_tower_summary": (
            f"Stage 6 benchmark tested {len(rows)} scenarios. Highest risk: "
            f"{top.get('scenario_name', 'N/A')} with priority {top.get('scenario_priority', 'N/A')} "
            f"and gap {top.get('scenario_gap', 0)}."
        ),
    }
