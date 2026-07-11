"""Stage 4 cost, waste, ROI, and executive-value analysis for MedPack AI.

Stage 4 does not replace the clinical/supply-chain recommendations from Stages 1-3.
It translates them into business/executive language: dollars at risk, waste exposure,
emergency-order premium, transfer savings, labor impact, and a simple ROI score.

All values are demo estimates for portfolio/capstone use, not audited financials.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, Dict, Iterable, Mapping, Optional

from backend.traceability import ensure_traceability_fields, load_inventory_state
from backend.task_manager import list_tasks
from backend.stage3_action_plan import build_stage3_action_plan
from backend.usable_stock import build_usable_stock_analysis

ASSUMPTION_PATH = "database/cost_assumptions.json"

DEFAULT_ASSUMPTIONS: Dict[str, Any] = {
    "stage": "Stage 4 - Cost, Waste & ROI Assumptions",
    "description": "Demo financial assumptions for MedPack AI executive-value reporting. Values are not audited hospital finance numbers.",
    "labor": {
        "supply_tech_hourly_cost": 28.0,
        "nurse_hourly_cost": 62.0,
        "default_transfer_minutes": 24.0,
        "nurse_search_minutes_saved_per_shortage_unit": 1.8,
        "packing_minutes_saved_per_prepacked_unit": 0.8
    },
    "risk": {
        "stockout_impact_multiplier": {
            "Low": 1.5,
            "Medium": 3.0,
            "High": 6.0,
            "Critical": 10.0
        },
        "emergency_order_fixed_fee": 180.0,
        "expiring_soon_window_days": 30,
        "overstock_carrying_cost_monthly_pct": 0.035,
        "rush_order_admin_minutes": 18.0,
        "escalation_admin_minutes": 25.0
    },
    "category_unit_cost_defaults": {
        "IV Supplies": 8.5,
        "PPE": 2.25,
        "Respiratory": 18.0,
        "Wound Care": 7.5,
        "Catheterization": 22.0,
        "Lab Supplies": 6.5,
        "Surgical Supplies": 95.0,
        "Monitoring": 28.0,
        "General": 10.0
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


def _load_assumptions() -> Dict[str, Any]:
    if not os.path.exists(ASSUMPTION_PATH):
        return DEFAULT_ASSUMPTIONS
    try:
        with open(ASSUMPTION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # merge shallow defaults to avoid KeyErrors if the file is edited
            merged = json.loads(json.dumps(DEFAULT_ASSUMPTIONS))
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
    except Exception:
        pass
    return DEFAULT_ASSUMPTIONS


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _parse_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def _selected_records(records: Iterable[Mapping[str, Any]], item: str, dept: str):
    item_n = _norm(item)
    dept_n = _norm(dept)
    return [dict(r) for r in records if _norm(r.get("item_name")) == item_n and _norm(r.get("department")) == dept_n]


def _infer_unit_cost(telemetry: Mapping[str, Any], records, assumptions: Mapping[str, Any]) -> float:
    explicit = _as_float(telemetry.get("unit_cost"), 0.0)
    # Stage 4 is interactive: prefer the dashboard's unit-cost input when present
    # so the user can test ROI sensitivity. Fall back to seeded inventory costs.
    if explicit > 0:
        return round(explicit, 2)
    costs = [_as_float(r.get("unit_cost"), 0.0) for r in records]
    costs = [c for c in costs if c > 0]
    if costs:
        return round(sum(costs) / len(costs), 2)
    category = str(telemetry.get("item_category") or "General")
    defaults = assumptions.get("category_unit_cost_defaults", {}) or {}
    return round(_as_float(defaults.get(category), _as_float(defaults.get("General"), 10.0)), 2)


def _inventory_waste_exposure(records, unit_cost: float, window_days: int) -> Dict[str, Any]:
    today = date.today()
    expired_units = recalled_units = expiring_soon_units = 0
    expiration_rows = []
    for rec in records:
        qty = max(0, _as_int(rec.get("current_stock"), 0))
        recall = str(rec.get("recall_status", "Clear") or "Clear").strip().lower()
        if recall not in {"", "clear", "none", "ok", "safe"}:
            recalled_units += qty
        exp = _parse_date(rec.get("expiration_date"))
        if exp is None:
            continue
        days = (exp - today).days
        if days < 0:
            expired_units += qty
        elif days <= window_days:
            expiring_soon_units += qty
            expiration_rows.append({
                "item_name": rec.get("item_name"),
                "department": rec.get("department"),
                "lot_number": rec.get("lot_number", ""),
                "expiration_date": rec.get("expiration_date", ""),
                "days_to_expire": days,
                "quantity": qty,
                "estimated_value": round(qty * unit_cost, 2),
            })
    waste_units = expired_units + recalled_units + expiring_soon_units
    return {
        "expired_units": int(expired_units),
        "recalled_units": int(recalled_units),
        "expiring_soon_units": int(expiring_soon_units),
        "waste_risk_units": int(waste_units),
        "expired_recalled_value": round((expired_units + recalled_units) * unit_cost, 2),
        "expiring_soon_value": round(expiring_soon_units * unit_cost, 2),
        "total_waste_risk_value": round(waste_units * unit_cost, 2),
        "expiration_rows": expiration_rows[:10],
    }


def build_stage4_roi_analysis(
    telemetry: Mapping[str, Any],
    predicted_24h_demand: Optional[float] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
    stage3_plan: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a Stage 4 executive/ROI view for the selected scenario."""
    telemetry = dict(telemetry or {})
    item = str(telemetry.get("item_name", "Unknown Item") or "Unknown Item")
    dept = str(telemetry.get("department", "Unknown Department") or "Unknown Department")
    assumptions = _load_assumptions()
    records = [dict(r) for r in (inventory_records if inventory_records is not None else (ensure_traceability_fields() or load_inventory_state(enrich=True)))]
    task_rows = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]

    if stage3_plan is None:
        stage3_plan = build_stage3_action_plan(
            telemetry,
            predicted_24h_demand=predicted_24h_demand,
            inventory_records=records,
            tasks=task_rows,
        )
    else:
        stage3_plan = dict(stage3_plan)

    predicted = _as_float(
        predicted_24h_demand if predicted_24h_demand is not None else stage3_plan.get("predicted_24h_demand", telemetry.get("predicted_24h_demand", 0.0)),
        0.0,
    )
    selected = _selected_records(records, item, dept)
    unit_cost = _infer_unit_cost(telemetry, selected, assumptions)

    usable = stage3_plan.get("stage2_usable_stock") or build_usable_stock_analysis(
        telemetry,
        predicted_24h_demand=predicted,
        inventory_records=records,
        tasks=task_rows,
    )
    transfer = stage3_plan.get("transfer_recommendation", {}) or {}
    supplier = stage3_plan.get("supplier_risk", {}) or {}
    substitute = stage3_plan.get("substitute_options", {}) or {}

    true_gap = max(0.0, _as_float(usable.get("true_shortage_gap"), stage3_plan.get("true_shortage_gap", 0)))
    risk_level = str(usable.get("risk_level") or (usable.get("shortage_risk_using_usable_stock") or {}).get("risk_level") or "Low")
    transfer_qty = max(0, _as_int(transfer.get("recommended_transfer_qty"), 0))
    post_transfer_gap = max(0.0, _as_float(stage3_plan.get("post_transfer_gap"), transfer.get("post_transfer_gap", true_gap)))
    vendor = supplier.get("recommended_vendor") or {}
    supplier_status = supplier.get("supplier_status", "")
    order_qty = max(0, _as_int(vendor.get("recommended_order_qty"), round(post_transfer_gap))) if post_transfer_gap > 0 else 0
    vendor_multiplier = _as_float(vendor.get("unit_cost_multiplier"), 1.0)
    substitute_best = substitute.get("best_substitute_option") or {}
    substitute_qty = max(0, _as_int(substitute_best.get("recommended_substitute_qty"), 0)) if substitute_best.get("acceptable") else 0

    risk_cfg = assumptions.get("risk", {}) or {}
    labor_cfg = assumptions.get("labor", {}) or {}
    impact_multiplier = _as_float((risk_cfg.get("stockout_impact_multiplier") or {}).get(risk_level), 3.0)
    stockout_value_per_unit = unit_cost * impact_multiplier
    nurse_hourly = _as_float(labor_cfg.get("nurse_hourly_cost"), 62.0)
    tech_hourly = _as_float(labor_cfg.get("supply_tech_hourly_cost"), 28.0)
    nurse_search_min = _as_float(labor_cfg.get("nurse_search_minutes_saved_per_shortage_unit"), 1.8)
    pack_saved_min = _as_float(labor_cfg.get("packing_minutes_saved_per_prepacked_unit"), 0.8)

    shortage_risk_value = true_gap * stockout_value_per_unit
    shortage_units_addressed = min(true_gap, transfer_qty + order_qty + substitute_qty)
    stockout_risk_value_protected = shortage_units_addressed * stockout_value_per_unit

    transfer_minutes = 0.0
    for opt in transfer.get("transfer_options", []) or []:
        if _as_int(opt.get("recommended_transfer_qty"), 0) > 0:
            transfer_minutes += _as_float(opt.get("estimated_transfer_minutes"), _as_float(labor_cfg.get("default_transfer_minutes"), 24.0))
    if transfer_qty > 0 and transfer_minutes <= 0:
        transfer_minutes = _as_float(labor_cfg.get("default_transfer_minutes"), 24.0)
    transfer_labor_cost = (transfer_minutes / 60.0) * tech_hourly
    transfer_savings_vs_emergency = max(0.0, transfer_qty * unit_cost * max(0.0, vendor_multiplier - 1.0))

    emergency_fixed_fee = _as_float(risk_cfg.get("emergency_order_fixed_fee"), 180.0)
    emergency_premium_cost = order_qty * unit_cost * max(0.0, vendor_multiplier - 1.0)
    emergency_order_cost = (order_qty * unit_cost * vendor_multiplier) + (emergency_fixed_fee if order_qty > 0 and vendor.get("emergency_order_available") else 0.0)
    supplier_delay_penalty = 0.0
    if post_transfer_gap > 0 and supplier_status in {"supplier_delay_risk", "no_supplier_solution"}:
        supplier_delay_penalty = post_transfer_gap * stockout_value_per_unit * 0.35

    window_days = _as_int(risk_cfg.get("expiring_soon_window_days"), 30)
    waste = _inventory_waste_exposure(selected, unit_cost, window_days)

    total_stock = _as_float(usable.get("total_stock"), telemetry.get("current_stock", 0.0))
    usable_stock = _as_float(usable.get("usable_stock"), telemetry.get("current_stock", 0.0))
    par_level = max(0, _as_int(telemetry.get("reorder_point"), 0))
    if selected:
        # Use seeded PAR if present; otherwise sidebar reorder point.
        par_values = [_as_int(r.get("par_level"), 0) for r in selected if _as_int(r.get("par_level"), 0) > 0]
        if par_values:
            par_level = int(round(sum(par_values) / len(par_values)))
    overstock_units = max(0.0, usable_stock - max(par_level, predicted))
    overstock_value = overstock_units * unit_cost
    carrying_pct = _as_float(risk_cfg.get("overstock_carrying_cost_monthly_pct"), 0.035)
    monthly_carrying_cost = overstock_value * carrying_pct

    nurse_time_saved_minutes = shortage_units_addressed * nurse_search_min
    packing_time_saved_minutes = max(0, _as_float(telemetry.get("pack_time_minutes"), 0.0) - pack_saved_min) * max(0, _as_int(telemetry.get("recommended_pack_quantity"), 0))
    if packing_time_saved_minutes <= 0:
        packing_time_saved_minutes = min(shortage_units_addressed, max(true_gap, 0)) * pack_saved_min
    labor_time_value = ((nurse_time_saved_minutes / 60.0) * nurse_hourly) + ((packing_time_saved_minutes / 60.0) * tech_hourly)

    gross_value_protected = stockout_risk_value_protected + waste.get("total_waste_risk_value", 0.0) + transfer_savings_vs_emergency + labor_time_value
    action_cost = transfer_labor_cost + emergency_premium_cost + supplier_delay_penalty
    net_value_estimate = gross_value_protected - action_cost
    roi_ratio = (gross_value_protected / action_cost) if action_cost > 0 else (gross_value_protected if gross_value_protected > 0 else 0.0)

    if true_gap <= 0 and waste.get("waste_risk_units", 0) <= 0 and overstock_units <= 0:
        executive_status = "stable"
        executive_recommendation = f"No immediate financial intervention required for {item} in {dept}; monitor forecast, PAR level, and expiry status."
    elif true_gap <= 0 and (waste.get("waste_risk_units", 0) > 0 or overstock_units > 0):
        executive_status = "waste_or_overstock_focus"
        executive_recommendation = f"Demand is covered, but reduce waste exposure for {item}: rotate expiring stock first and avoid extra replenishment until overstock falls."
    elif net_value_estimate > 0:
        executive_status = "positive_value_action"
        executive_recommendation = f"Approve the Stage 3 action plan: it protects an estimated ${net_value_estimate:,.0f} in shortage/waste/labor risk value after action costs."
    else:
        executive_status = "action_needed_low_financial_return"
        executive_recommendation = f"Operational action is still needed for {item}, but finance value is tight; prioritize clinical risk and use the lowest-cost safe option."

    return {
        "stage": "Stage 4 - Cost, Waste & ROI Executive Dashboard",
        "item_name": item,
        "department": dept,
        "predicted_24h_demand": round(predicted, 2),
        "unit_cost_used": round(unit_cost, 2),
        "risk_level": risk_level,
        "true_shortage_gap": round(true_gap, 2),
        "shortage_risk_value": round(shortage_risk_value, 2),
        "stockout_risk_value_protected": round(stockout_risk_value_protected, 2),
        "transfer_qty": int(transfer_qty),
        "transfer_labor_cost": round(transfer_labor_cost, 2),
        "transfer_savings_vs_emergency": round(transfer_savings_vs_emergency, 2),
        "supplier_order_qty": int(order_qty),
        "emergency_order_cost": round(emergency_order_cost, 2),
        "emergency_premium_cost": round(emergency_premium_cost, 2),
        "supplier_delay_penalty": round(supplier_delay_penalty, 2),
        "waste_risk": waste,
        "overstock_units": round(overstock_units, 2),
        "overstock_value": round(overstock_value, 2),
        "monthly_carrying_cost": round(monthly_carrying_cost, 2),
        "nurse_time_saved_minutes": round(nurse_time_saved_minutes, 1),
        "packing_time_saved_minutes": round(packing_time_saved_minutes, 1),
        "labor_time_value": round(labor_time_value, 2),
        "gross_value_protected": round(gross_value_protected, 2),
        "estimated_action_cost": round(action_cost, 2),
        "net_value_estimate": round(net_value_estimate, 2),
        "roi_ratio": round(roi_ratio, 2),
        "executive_status": executive_status,
        "executive_recommendation": executive_recommendation,
        "stage3_best_action": stage3_plan.get("best_action"),
        "stage3_final_recommendation": stage3_plan.get("final_recommendation"),
        "assumptions_used": {
            "unit_cost_source": "inventory_state_or_sidebar_or_category_default",
            "stockout_impact_multiplier": impact_multiplier,
            "expiring_soon_window_days": window_days,
            "overstock_carrying_cost_monthly_pct": carrying_pct,
            "note": "Demo estimates for portfolio/capstone storytelling; not audited financial guidance.",
        },
        "control_tower_summary": (
            f"Stage 4 value view for {item} in {dept}: shortage risk value ${shortage_risk_value:,.0f}, "
            f"waste risk ${waste.get('total_waste_risk_value', 0.0):,.0f}, net estimated value ${net_value_estimate:,.0f}. "
            f"Executive status: {executive_status}."
        ),
    }


def load_stage4_assumptions() -> Dict[str, Any]:
    """Expose the assumptions for the dashboard/reference endpoint."""
    return _load_assumptions()
