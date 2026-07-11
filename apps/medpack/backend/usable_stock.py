"""Stage 2 usable-stock intelligence.

This module connects the Stage 1 traceability layer to the original forecast.
Instead of judging risk against total stock only, it calculates what stock is
actually usable after expired/recalled lots and already-open packing tasks are
removed. It also finds transfer candidates in other departments.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.shortage_rules import calculate_shortage_risk
from backend.task_manager import list_tasks
from backend.traceability import enrich_record, load_inventory_state

ACTIVE_TASK_STATUSES = {"NEW", "ASSIGNED", "PICKING", "PACKED", "ESCALATED"}
FINAL_TASK_STATUSES = {"DELIVERED", "CANCELLED"}
CLEAR_RECALL_VALUES = {"", "clear", "none", "no", "not recalled", "ok"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    return int(round(_as_float(value, float(default))))


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    for parser in (
        lambda v: datetime.fromisoformat(v).date(),
        lambda v: datetime.strptime(v, "%Y-%m-%d").date(),
        lambda v: datetime.strptime(v, "%m/%d/%Y").date(),
    ):
        try:
            return parser(text)
        except ValueError:
            continue
    return None


def _is_recalled(record: Mapping[str, Any]) -> bool:
    return _norm(record.get("recall_status", "Clear")) not in CLEAR_RECALL_VALUES


def _days_until_expiration(record: Mapping[str, Any]) -> Optional[int]:
    exp = _parse_date(record.get("expiration_date"))
    if exp is None:
        return None
    return (exp - datetime.now().date()).days


def _is_expired(record: Mapping[str, Any]) -> bool:
    days_left = _days_until_expiration(record)
    return days_left is not None and days_left < 0


def _is_expiring_soon(record: Mapping[str, Any], window_days: int = 30) -> bool:
    days_left = _days_until_expiration(record)
    return days_left is not None and 0 <= days_left <= window_days


def _find_inventory_record(
    records: Iterable[Mapping[str, Any]], item_name: str, department: str
) -> Optional[Dict[str, Any]]:
    item_key = _norm(item_name)
    dept_key = _norm(department)
    for record in records:
        if _norm(record.get("item_name")) == item_key and _norm(record.get("department")) == dept_key:
            return dict(record)
    return None


def _active_task_quantity(
    item_name: str,
    department: str,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
) -> int:
    item_key = _norm(item_name)
    dept_key = _norm(department)
    qty = 0
    for task in list(tasks) if tasks is not None else list_tasks(limit=500):
        status = str(task.get("status", "")).strip().upper()
        if status in FINAL_TASK_STATUSES or status not in ACTIVE_TASK_STATUSES:
            continue
        if _norm(task.get("item_name")) == item_key and _norm(task.get("department")) == dept_key:
            qty += max(0, _as_int(task.get("quantity"), 0))
    return qty


def _record_stock_breakdown(
    record: Mapping[str, Any],
    assigned_qty: int = 0,
    override_total_stock: Optional[int] = None,
    expiration_window_days: int = 30,
) -> Dict[str, Any]:
    total_stock = max(0, _as_int(override_total_stock if override_total_stock is not None else record.get("current_stock", 0), 0))
    expired = _is_expired(record)
    recalled = _is_recalled(record)
    expiring_soon = _is_expiring_soon(record, window_days=expiration_window_days)
    days_left = _days_until_expiration(record)

    # The current app stores one traceability row per item/department, not one row per lot.
    # Therefore if that row is expired or recalled, all units in that row are treated as unsafe.
    unsafe_stock = total_stock if expired or recalled else 0
    expired_stock = total_stock if expired else 0
    recalled_stock = total_stock if recalled else 0
    expiring_soon_stock = total_stock if expiring_soon and not expired and not recalled else 0

    assignable_pool = max(0, total_stock - unsafe_stock)
    active_task_reserved_stock = min(assignable_pool, max(0, assigned_qty))
    usable_stock = max(0, assignable_pool - active_task_reserved_stock)

    return {
        "total_stock": total_stock,
        "usable_stock": usable_stock,
        "unsafe_stock": unsafe_stock,
        "expired_stock": expired_stock,
        "recalled_stock": recalled_stock,
        "expiring_soon_stock": expiring_soon_stock,
        "active_task_reserved_stock": active_task_reserved_stock,
        "days_until_expiration": days_left,
        "is_expired": expired,
        "is_recalled": recalled,
        "is_expiring_soon": expiring_soon,
        "par_level": _as_int(record.get("par_level", record.get("reorder_point", 0)), 0),
        "location": record.get("location", ""),
        "lot_number": record.get("lot_number", ""),
        "barcode": record.get("barcode", ""),
        "udi_code": record.get("udi_code", ""),
        "recall_status": record.get("recall_status", "Clear"),
        "expiration_date": record.get("expiration_date", ""),
    }


def _build_stage2_action(
    item_name: str,
    department: str,
    predicted_demand: float,
    local: Mapping[str, Any],
    transfer_candidate_stock: int,
) -> str:
    shortage_gap = float(predicted_demand) - float(local.get("usable_stock", 0))
    unsafe = int(local.get("unsafe_stock", 0) or 0)
    reserved = int(local.get("active_task_reserved_stock", 0) or 0)

    if shortage_gap <= 0 and unsafe <= 0 and reserved <= 0:
        return f"No immediate action: usable stock for {item_name} in {department} covers the forecast. Continue normal scan tracking."

    actions: List[str] = []
    if unsafe > 0:
        actions.append(f"remove/quarantine {unsafe} unsafe units before counting stock")
    if reserved > 0:
        actions.append(f"respect {reserved} units already tied to active packing tasks")
    if shortage_gap > 0:
        if transfer_candidate_stock > 0:
            move_qty = min(int(round(shortage_gap)), transfer_candidate_stock)
            actions.append(f"transfer up to {move_qty} units from another department")
        remaining = max(0, int(round(shortage_gap - transfer_candidate_stock)))
        pack_qty = int(round(shortage_gap)) if transfer_candidate_stock <= 0 else remaining
        if pack_qty > 0:
            actions.append(f"pack/reorder {pack_qty} additional units")
    return "Stage 2 action: " + "; ".join(actions) + "."


def build_usable_stock_analysis(
    telemetry: Mapping[str, Any],
    predicted_24h_demand: Optional[float] = None,
    inventory_records: Optional[Iterable[Mapping[str, Any]]] = None,
    tasks: Optional[Iterable[Mapping[str, Any]]] = None,
    expiration_window_days: int = 30,
) -> Dict[str, Any]:
    """Return forecast-vs-usable-stock analysis for the selected item/department."""
    item_name = str(telemetry.get("item_name", "Unknown Item") or "Unknown Item")
    department = str(telemetry.get("department", "Unknown Department") or "Unknown Department")
    predicted = _as_float(predicted_24h_demand if predicted_24h_demand is not None else telemetry.get("predicted_24h_demand", 0.0), 0.0)

    records = [dict(r) for r in (inventory_records if inventory_records is not None else load_inventory_state(enrich=True))]
    tasks_list = [dict(t) for t in (tasks if tasks is not None else list_tasks(limit=500))]

    matched = _find_inventory_record(records, item_name, department)
    if matched is None:
        matched = enrich_record(dict(telemetry), index=0)

    assigned_qty = _active_task_quantity(item_name, department, tasks=tasks_list)
    override_stock = _as_int(telemetry.get("current_stock"), 0) if "current_stock" in telemetry else None
    local = _record_stock_breakdown(
        matched,
        assigned_qty=assigned_qty,
        override_total_stock=override_stock,
        expiration_window_days=expiration_window_days,
    )

    item_key = _norm(item_name)
    dept_key = _norm(department)
    wrong_location_stock = 0
    transfer_candidate_stock = 0
    transfer_options: List[Dict[str, Any]] = []
    for record in records:
        if _norm(record.get("item_name")) != item_key or _norm(record.get("department")) == dept_key:
            continue
        other_dept = str(record.get("department", "Unknown Department"))
        other_assigned = _active_task_quantity(item_name, other_dept, tasks=tasks_list)
        other = _record_stock_breakdown(record, assigned_qty=other_assigned, expiration_window_days=expiration_window_days)
        wrong_location_stock += int(other["usable_stock"])
        excess_above_par = max(0, int(other["usable_stock"]) - int(other.get("par_level", 0) or 0))
        transfer_candidate_stock += excess_above_par
        if excess_above_par > 0:
            transfer_options.append({
                "source_department": other_dept,
                "source_location": other.get("location", ""),
                "usable_stock": int(other["usable_stock"]),
                "par_level": int(other.get("par_level", 0) or 0),
                "transferable_units": excess_above_par,
                "lot_number": other.get("lot_number", ""),
                "expiration_date": other.get("expiration_date", ""),
                "recall_status": other.get("recall_status", "Clear"),
            })

    transfer_options.sort(key=lambda r: r.get("transferable_units", 0), reverse=True)
    usable_stock = int(local["usable_stock"])
    true_shortage_gap = round(predicted - usable_stock, 2)
    post_transfer_gap = round(predicted - (usable_stock + transfer_candidate_stock), 2)

    shortage_result = calculate_shortage_risk(predicted, usable_stock)
    shortage_result.update({
        "stock_basis": "usable_stock",
        "total_stock": int(local["total_stock"]),
        "usable_stock": usable_stock,
        "unsafe_stock": int(local["unsafe_stock"]),
        "expired_stock": int(local["expired_stock"]),
        "recalled_stock": int(local["recalled_stock"]),
        "expiring_soon_stock": int(local["expiring_soon_stock"]),
        "active_task_reserved_stock": int(local["active_task_reserved_stock"]),
        "transfer_candidate_stock": int(transfer_candidate_stock),
        "wrong_location_stock": int(wrong_location_stock),
        "true_shortage_gap": true_shortage_gap,
        "post_transfer_gap": post_transfer_gap,
        "reasoning": (
            shortage_result.get("reasoning", "")
            + f" Stage 2 basis: risk is calculated against usable stock ({usable_stock}), not total stock ({local['total_stock']})."
        ),
    })

    safety_notes: List[str] = []
    if local["unsafe_stock"]:
        safety_notes.append("Some local stock is expired or recalled and was removed from usable stock.")
    if local["active_task_reserved_stock"]:
        safety_notes.append("Some local stock is already tied to active packing tasks and was removed from available stock.")
    if local["expiring_soon_stock"]:
        safety_notes.append("Some stock expires soon; rotate it first if it is still safe to use.")
    if transfer_candidate_stock:
        safety_notes.append("Other departments have excess usable stock above PAR that may be transferred before emergency ordering.")
    if not safety_notes:
        safety_notes.append("No expired, recalled, or task-reserved local stock detected for this item/department.")

    action = _build_stage2_action(item_name, department, predicted, local, transfer_candidate_stock)

    return {
        "stage": "Stage 2 - Forecast + Usable Stock Integration",
        "item_name": item_name,
        "department": department,
        "predicted_24h_demand": round(predicted, 2),
        "stock_basis": "usable_stock",
        "total_stock": int(local["total_stock"]),
        "usable_stock": usable_stock,
        "unsafe_stock": int(local["unsafe_stock"]),
        "expired_stock": int(local["expired_stock"]),
        "recalled_stock": int(local["recalled_stock"]),
        "expiring_soon_stock": int(local["expiring_soon_stock"]),
        "active_task_reserved_stock": int(local["active_task_reserved_stock"]),
        "wrong_location_stock": int(wrong_location_stock),
        "transfer_candidate_stock": int(transfer_candidate_stock),
        "effective_stock_after_transfer": int(usable_stock + transfer_candidate_stock),
        "true_shortage_gap": true_shortage_gap,
        "post_transfer_gap": post_transfer_gap,
        "risk_level": shortage_result.get("risk_level"),
        "coverage_ratio": shortage_result.get("coverage_ratio"),
        "recommended_stage2_action": action,
        "safety_notes": safety_notes,
        "local_inventory_snapshot": local,
        "top_transfer_options": transfer_options[:5],
        "shortage_risk_using_usable_stock": shortage_result,
        "explanation": (
            "Stage 2 connects the forecast to traceability: total stock is adjusted by removing expired/recalled units "
            "and stock already reserved by active tasks, then the forecast is compared to true usable stock."
        ),
    }
