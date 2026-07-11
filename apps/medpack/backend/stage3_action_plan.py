"""Stage 3 supplier, transfer and substitute action-plan orchestrator."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from backend.traceability import ensure_traceability_fields, load_inventory_state
from backend.task_manager import list_tasks
from backend.usable_stock import build_usable_stock_analysis
from backend.transfer_optimizer import build_transfer_recommendation
from backend.supplier_risk import build_supplier_risk
from backend.substitution_engine import build_substitute_options


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_stage3_action_plan(
    telemetry: Mapping[str, Any],
    predicted_24h_demand: Optional[float] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a complete Stage 3 action plan.

    Stage 3 chooses a practical sequence: internal transfer first, supplier order
    second, substitute third, escalation when no safe option closes the gap.
    """
    telemetry = dict(telemetry or {})
    item = str(telemetry.get("item_name", "Unknown Item") or "Unknown Item")
    dept = str(telemetry.get("department", "Unknown Department") or "Unknown Department")
    predicted = _as_float(predicted_24h_demand if predicted_24h_demand is not None else telemetry.get("predicted_24h_demand", 0.0), 0.0)

    records = [dict(r) for r in (inventory_records if inventory_records is not None else (ensure_traceability_fields() or load_inventory_state(enrich=True)))]
    task_rows = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]

    usable = build_usable_stock_analysis(
        telemetry,
        predicted_24h_demand=predicted,
        inventory_records=records,
        tasks=task_rows,
    )
    transfer = build_transfer_recommendation(
        telemetry,
        predicted_24h_demand=predicted,
        usable_analysis=usable,
        inventory_records=records,
        tasks=task_rows,
    )
    supplier = build_supplier_risk(
        telemetry,
        shortage_gap=usable.get("true_shortage_gap", 0),
        post_transfer_gap=transfer.get("post_transfer_gap", 0),
    )
    substitute = build_substitute_options(
        telemetry,
        remaining_gap=transfer.get("post_transfer_gap", 0),
        inventory_records=records,
        tasks=task_rows,
    )

    true_gap = max(0.0, _as_float(usable.get("true_shortage_gap"), 0.0))
    post_transfer_gap = max(0.0, _as_float(transfer.get("post_transfer_gap"), 0.0))
    transfer_qty = int(transfer.get("recommended_transfer_qty", 0) or 0)
    supplier_vendor = supplier.get("recommended_vendor") or {}
    substitute_best = substitute.get("best_substitute_option") or {}

    sequence = []
    if true_gap <= 0:
        final_status = "covered_by_usable_stock"
        sequence.append(f"No emergency action: {item} in {dept} has enough usable stock for the forecast.")
    else:
        final_status = "action_required"
        if transfer_qty > 0:
            sequence.append(f"Transfer {transfer_qty} units internally before placing emergency orders.")
        if post_transfer_gap > 0:
            vendor_qty = supplier_vendor.get("recommended_order_qty", int(round(post_transfer_gap))) if supplier_vendor else int(round(post_transfer_gap))
            vendor_name = supplier_vendor.get("vendor_name", "backup/emergency supplier") if supplier_vendor else "backup/emergency supplier"
            sequence.append(f"Order {vendor_qty} units from {vendor_name} for the remaining gap.")
            if substitute_best and substitute_best.get("acceptable"):
                sequence.append(f"Use {substitute_best.get('recommended_substitute_qty', 0)} units of {substitute_best.get('substitute_item')} only if transfer/order timing does not cover the floor need.")
        if not sequence:
            sequence.append("Escalate to supply supervisor: no transfer, supplier, or substitute path closes the gap.")

    if true_gap <= 0:
        best_action = "Monitor only"
    elif transfer_qty >= true_gap:
        best_action = "Internal transfer"
    elif supplier_vendor and supplier.get("supplier_status") in {"supplier_can_cover", "supplier_delay_risk"}:
        best_action = "Transfer + supplier order" if transfer_qty > 0 else "Supplier order"
    elif substitute_best and substitute_best.get("acceptable"):
        best_action = "Approved substitute"
    else:
        best_action = "Escalate"

    final_recommendation = " ".join(sequence)
    if true_gap > 0 and best_action == "Escalate":
        final_recommendation += " Notify materials management and clinical leadership."

    return {
        "stage": "Stage 3 - Supplier + Transfer Intelligence",
        "item_name": item,
        "department": dept,
        "predicted_24h_demand": round(predicted, 2),
        "true_shortage_gap": round(true_gap, 2),
        "post_transfer_gap": round(post_transfer_gap, 2),
        "best_action": best_action,
        "final_status": final_status,
        "recommended_sequence": sequence,
        "final_recommendation": final_recommendation,
        "stage2_usable_stock": usable,
        "transfer_recommendation": transfer,
        "supplier_risk": supplier,
        "substitute_options": substitute,
        "control_tower_summary": (
            f"Stage 3 action plan for {item} in {dept}: best action is {best_action}. "
            f"True gap={round(true_gap, 2)}, internal transfer={transfer_qty}, post-transfer gap={round(post_transfer_gap, 2)}."
        ),
    }
