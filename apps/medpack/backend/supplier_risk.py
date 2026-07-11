"""Stage 3 supplier risk and vendor choice intelligence."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Mapping, Optional

VENDOR_PATH = "database/vendor_state.json"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_vendor_state() -> Dict[str, Any]:
    if not os.path.exists(VENDOR_PATH):
        return {"vendors": [], "default_sla_hours": {}}
    with open(VENDOR_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"vendors": [], "default_sla_hours": {}}
    return data


def _vendor_matches_category(vendor: Mapping[str, Any], category: str) -> bool:
    focus = vendor.get("category_focus") or []
    return not focus or str(category) in {str(x) for x in focus}


def _vendor_score(vendor: Mapping[str, Any], urgency_hours: float, clinical_criticality: float) -> float:
    delay_days = _as_float(vendor.get("current_delay_days"), _as_float(vendor.get("normal_lead_time_days"), 2.0))
    delay_hours = delay_days * 24.0
    reliability = _as_float(vendor.get("reliability_score"), 0.8)
    backorder = _as_float(vendor.get("backorder_probability"), 0.2)
    cost = _as_float(vendor.get("unit_cost_multiplier"), 1.0)
    emergency_bonus = 0.15 if vendor.get("emergency_order_available") else 0.0
    speed_score = max(0.0, 1.0 - (delay_hours / max(urgency_hours, 1.0))) if urgency_hours > 0 else 0.6
    critical_bonus = 0.08 * clinical_criticality if delay_hours <= urgency_hours else -0.05 * clinical_criticality
    return round((speed_score * 0.36 + reliability * 0.34 + (1 - backorder) * 0.20 + emergency_bonus + critical_bonus - max(0, cost - 1.0) * 0.10) * 100, 2)


def build_supplier_risk(
    telemetry: Mapping[str, Any],
    shortage_gap: Optional[float] = None,
    post_transfer_gap: Optional[float] = None,
) -> Dict[str, Any]:
    """Compare vendors and recommend a supplier action."""
    telemetry = dict(telemetry or {})
    item = str(telemetry.get("item_name", "Unknown Item") or "Unknown Item")
    dept = str(telemetry.get("department", "Unknown Department") or "Unknown Department")
    category = str(telemetry.get("item_category", "General") or "General")
    gap = max(0.0, _as_float(post_transfer_gap if post_transfer_gap is not None else shortage_gap, 0.0))
    clinical = _as_float(telemetry.get("clinical_criticality"), 3.0)
    supplier_delay_slider = _as_float(telemetry.get("supplier_delay_days"), 2.0)

    # Shortage window is intentionally simple for demo: critical shortages need a fix inside the next shift.
    urgency_hours = 8.0 if clinical >= 4 or gap >= 30 else 12.0 if gap >= 15 else 24.0
    state = _load_vendor_state()
    vendors = [dict(v) for v in state.get("vendors", []) if _vendor_matches_category(v, category)]
    if not vendors:
        vendors = [dict(v) for v in state.get("vendors", [])]

    ranked: List[Dict[str, Any]] = []
    for vendor in vendors:
        # Blend demo vendor delay with the live sidebar delay so sliders visibly matter.
        base_delay = _as_float(vendor.get("current_delay_days"), _as_float(vendor.get("normal_lead_time_days"), 2.0))
        adjusted_delay = round(max(0.25, (base_delay * 0.65) + (supplier_delay_slider * 0.35)), 2)
        vendor["adjusted_delay_days"] = adjusted_delay
        vendor["adjusted_delay_hours"] = round(adjusted_delay * 24, 1)
        vendor["can_meet_shortage_window"] = vendor["adjusted_delay_hours"] <= urgency_hours
        vendor["supplier_score"] = _vendor_score({**vendor, "current_delay_days": adjusted_delay}, urgency_hours, clinical)
        if gap <= 0:
            vendor["recommended_order_qty"] = 0
        else:
            buffer = 0.35 if clinical >= 4 else 0.25 if clinical >= 3 else 0.15
            vendor["recommended_order_qty"] = int(round(gap * (1.0 + buffer)))
        ranked.append(vendor)

    ranked.sort(key=lambda v: (v.get("can_meet_shortage_window", False), v.get("supplier_score", 0)), reverse=True)
    best = ranked[0] if ranked else None
    primary = next((v for v in ranked if str(v.get("role", "")).lower() == "primary"), best)
    backup = next((v for v in ranked if str(v.get("role", "")).lower() in {"backup", "emergency"} and v != primary), None)

    if gap <= 0:
        status = "no_order_needed"
        recommendation = f"No supplier order required for {item}; usable/internal coverage is enough for the forecast window."
    elif best and best.get("can_meet_shortage_window"):
        status = "supplier_can_cover"
        recommendation = f"Use {best.get('vendor_name')} for {best.get('recommended_order_qty')} units; it is the best supplier fit for the shortage window."
    elif backup:
        status = "supplier_delay_risk"
        recommendation = f"Supplier delay risk remains. Place backup order with {backup.get('vendor_name')} and escalate if no internal transfer/substitute closes the gap."
    else:
        status = "no_supplier_solution"
        recommendation = "No vendor can confidently meet the shortage window; escalate to operations leadership."

    return {
        "stage": "Stage 3 - Supplier Delay & Backup Vendor Intelligence",
        "item_name": item,
        "department": dept,
        "item_category": category,
        "gap_after_transfer": round(gap, 2),
        "urgency_hours": urgency_hours,
        "supplier_status": status,
        "primary_vendor": primary,
        "backup_vendor": backup,
        "recommended_vendor": best,
        "ranked_vendors": ranked[:5],
        "recommendation": recommendation,
        "control_tower_note": "Supplier scores combine live supplier-delay slider, demo vendor reliability, backorder probability, emergency availability, cost multiplier and clinical urgency.",
    }
