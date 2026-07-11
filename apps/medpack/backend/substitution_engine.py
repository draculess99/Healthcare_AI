"""Stage 3 approved-substitute recommendation engine."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.usable_stock import build_usable_stock_analysis
from backend.traceability import load_inventory_state
from backend.task_manager import list_tasks

SUBSTITUTION_PATH = "database/substitution_rules.json"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_rules() -> Dict[str, Any]:
    if not os.path.exists(SUBSTITUTION_PATH):
        return {"rules": {}}
    with open(SUBSTITUTION_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"rules": {}}
    return data


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def build_substitute_options(
    telemetry: Mapping[str, Any],
    remaining_gap: Optional[float] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return approved substitute candidates and their available usable stock."""
    telemetry = dict(telemetry or {})
    item = str(telemetry.get("item_name", "Unknown Item") or "Unknown Item")
    dept = str(telemetry.get("department", "Unknown Department") or "Unknown Department")
    gap = max(0.0, _as_float(remaining_gap if remaining_gap is not None else telemetry.get("remaining_gap", 0.0), 0.0))
    clinical = _as_float(telemetry.get("clinical_criticality"), 3.0)

    records = [dict(r) for r in (inventory_records if inventory_records is not None else load_inventory_state(enrich=True))]
    task_rows = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]
    rules = _load_rules().get("rules", {})
    raw_candidates = rules.get(item, []) or rules.get(str(item).strip(), []) or []

    candidates: List[Dict[str, Any]] = []
    for raw in raw_candidates:
        sub_item = str(raw.get("substitute_item", "") or "").strip()
        if not sub_item:
            continue
        # Evaluate substitute in the target department first.
        sub_payload = {**telemetry, "item_name": sub_item, "department": dept, "current_stock": None}
        sub_payload.pop("current_stock", None)
        sub_analysis = build_usable_stock_analysis(
            sub_payload,
            predicted_24h_demand=0,
            inventory_records=records,
            tasks=task_rows,
        )
        local_usable = int(sub_analysis.get("usable_stock", 0) or 0)
        transferable = int(sub_analysis.get("transfer_candidate_stock", 0) or 0)
        total_available = local_usable + transferable
        suitability = _as_float(raw.get("suitability_score"), 0.0)
        clinical_fit = str(raw.get("clinical_fit", "Unknown"))
        # Criticality suppresses partial/suboptimal substitutes.
        critical_penalty = 0.12 if clinical >= 4 and suitability < 0.70 else 0.0
        score = round(max(0, suitability - critical_penalty) * 100 + min(total_available, max(gap, 1)) * 0.8, 2)
        candidates.append({
            "primary_item": item,
            "substitute_item": sub_item,
            "department": dept,
            "clinical_fit": clinical_fit,
            "suitability_score": suitability,
            "local_usable_stock": local_usable,
            "transferable_substitute_stock": transferable,
            "total_available_substitute_stock": total_available,
            "recommended_substitute_qty": int(min(round(gap), total_available)) if gap > 0 else 0,
            "substitution_score": score,
            "acceptable": bool(suitability >= 0.55 and total_available > 0),
            "notes": raw.get("notes", ""),
        })

    candidates.sort(key=lambda c: (c.get("acceptable", False), c.get("substitution_score", 0)), reverse=True)
    best = candidates[0] if candidates else None

    if gap <= 0:
        status = "not_needed"
        recommendation = f"No substitute required for {item}; the shortage gap is already closed."
    elif best and best.get("acceptable") and best.get("recommended_substitute_qty", 0) >= gap:
        status = "substitute_solves_gap"
        recommendation = f"Use {best.get('recommended_substitute_qty')} units of {best.get('substitute_item')} as an approved substitute if clinical policy allows."
    elif best and best.get("acceptable"):
        status = "partial_substitute"
        recommendation = f"Use {best.get('recommended_substitute_qty')} units of {best.get('substitute_item')} as partial coverage, then order/escalate the remaining gap."
    elif candidates:
        status = "substitute_not_recommended"
        recommendation = "Substitute candidates exist, but none are strong enough or available enough for this shortage."
    else:
        status = "no_substitute_rule"
        recommendation = f"No approved substitute rule is configured for {item}."

    return {
        "stage": "Stage 3 - Substitute Item Intelligence",
        "item_name": item,
        "department": dept,
        "remaining_gap": round(gap, 2),
        "substitution_status": status,
        "best_substitute_option": best,
        "substitute_options": candidates[:5],
        "recommendation": recommendation,
        "control_tower_note": "Substitutions are demo rules only. In a real hospital, these would require clinical governance/pharmacy/materials-management approval.",
    }
