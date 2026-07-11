"""Stage 3 transfer intelligence for MedPack AI.

This module turns the Stage 2 "wrong-location stock" insight into an operational
recommendation: whether another department can safely transfer excess usable
stock above its own PAR before emergency ordering is needed.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.usable_stock import build_usable_stock_analysis
from backend.traceability import load_inventory_state
from backend.task_manager import list_tasks


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    return int(round(_as_float(value, float(default))))


def _risk_rank(risk: str) -> int:
    return {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}.get(str(risk), 1)


def build_transfer_recommendation(
    telemetry: Mapping[str, Any],
    predicted_24h_demand: Optional[float] = None,
    usable_analysis: Optional[Mapping[str, Any]] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return ranked transfer options for the selected item/department."""
    telemetry = dict(telemetry or {})
    item = str(telemetry.get("item_name", "Unknown Item") or "Unknown Item")
    dept = str(telemetry.get("department", "Unknown Department") or "Unknown Department")
    predicted = _as_float(predicted_24h_demand if predicted_24h_demand is not None else telemetry.get("predicted_24h_demand", 0.0))

    records = [dict(r) for r in (inventory_records if inventory_records is not None else load_inventory_state(enrich=True))]
    task_rows = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]

    if usable_analysis is None:
        usable_analysis = build_usable_stock_analysis(
            telemetry,
            predicted_24h_demand=predicted,
            inventory_records=records,
            tasks=task_rows,
        )

    true_gap = max(0, _as_float(usable_analysis.get("true_shortage_gap"), 0.0))
    risk_level = str(usable_analysis.get("risk_level", "Low"))
    transfer_options = []
    running_remaining = true_gap

    for raw in usable_analysis.get("top_transfer_options", []) or []:
        transferable = max(0, _as_int(raw.get("transferable_units"), 0))
        if transferable <= 0:
            continue
        qty = min(transferable, max(0, int(round(running_remaining)))) if true_gap > 0 else 0
        estimated_minutes = 18 + (6 * len(transfer_options)) + (4 if _risk_rank(risk_level) >= 3 else 0)
        source_dept = raw.get("source_department", "Unknown")
        score = round((min(transferable, max(true_gap, 1)) * 2.5) + (_risk_rank(risk_level) * 12) - estimated_minutes * 0.15, 2)
        transfer_options.append({
            "source_department": source_dept,
            "target_department": dept,
            "item_name": item,
            "source_location": raw.get("source_location", ""),
            "source_usable_stock": raw.get("usable_stock", 0),
            "source_par_level": raw.get("par_level", 0),
            "transferable_units": transferable,
            "recommended_transfer_qty": max(0, qty),
            "estimated_transfer_minutes": estimated_minutes,
            "transfer_score": score,
            "lot_number": raw.get("lot_number", ""),
            "expiration_date": raw.get("expiration_date", ""),
            "recall_status": raw.get("recall_status", "Clear"),
            "reason": f"{source_dept} has {transferable} usable units above PAR that can cover {dept}'s gap before vendor delivery.",
        })
        running_remaining = max(0, running_remaining - qty)

    transfer_options.sort(key=lambda r: (r.get("recommended_transfer_qty", 0), r.get("transfer_score", 0)), reverse=True)
    recommended_qty = sum(int(x.get("recommended_transfer_qty", 0) or 0) for x in transfer_options)
    post_transfer_gap = max(0, round(true_gap - recommended_qty, 2))

    if true_gap <= 0:
        recommendation = f"No transfer required: usable stock for {item} in {dept} already covers the 24-hour forecast."
        status = "not_needed"
    elif transfer_options and recommended_qty >= true_gap:
        recommendation = f"Transfer {recommended_qty} units of {item} into {dept}; internal transfer can close the full shortage before ordering."
        status = "transfer_solves_gap"
    elif transfer_options and recommended_qty > 0:
        recommendation = f"Transfer {recommended_qty} units of {item} into {dept}, then cover the remaining {post_transfer_gap} units through supplier/substitute action."
        status = "partial_transfer"
    else:
        recommendation = f"No safe internal transfer found for {item}; move to supplier or approved-substitute action."
        status = "no_transfer_available"

    return {
        "stage": "Stage 3 - Multi-Location Transfer Intelligence",
        "item_name": item,
        "department": dept,
        "predicted_24h_demand": round(predicted, 2),
        "true_shortage_gap": round(true_gap, 2),
        "transfer_status": status,
        "recommended_transfer_qty": int(recommended_qty),
        "post_transfer_gap": post_transfer_gap,
        "transfer_options": transfer_options[:5],
        "best_transfer_option": transfer_options[0] if transfer_options else None,
        "recommendation": recommendation,
        "control_tower_note": "Stage 3 uses Stage 2 usable-stock output and only transfers stock that appears above the source department's PAR level.",
    }
