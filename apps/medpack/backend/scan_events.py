"""Barcode/UDI scan event simulator for Stage 1."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from backend.traceability import load_inventory_state, save_inventory_state

SCAN_EVENTS_PATH = "database/scan_events.jsonl"

VALID_SCAN_EVENTS = [
    "RECEIVED",
    "STOCKED",
    "PICKED",
    "PACKED",
    "DELIVERED",
    "CONSUMED",
    "WASTED_EXPIRED",
    "RECALLED_REMOVED",
]

STOCK_DELTAS = {
    "RECEIVED": 1,
    "STOCKED": 1,
    "PICKED": -1,
    "PACKED": 0,
    "DELIVERED": 0,
    "CONSUMED": -1,
    "WASTED_EXPIRED": -1,
    "RECALLED_REMOVED": -1,
}


def list_scan_events(limit: int = 25) -> List[Dict[str, Any]]:
    if not os.path.exists(SCAN_EVENTS_PATH):
        return []
    events: List[Dict[str, Any]] = []
    with open(SCAN_EVENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events[-limit:]


def _find_record(records: List[Dict[str, Any]], payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    barcode = str(payload.get("barcode", "")).strip()
    item_name = str(payload.get("item_name", "")).strip()
    department = str(payload.get("department", "")).strip()
    for rec in records:
        if barcode and barcode == str(rec.get("barcode", "")):
            return rec
    for rec in records:
        if item_name and department and rec.get("item_name") == item_name and rec.get("department") == department:
            return rec
    return None


def append_scan_event(payload: Mapping[str, Any]) -> Dict[str, Any]:
    event_type = str(payload.get("event_type", "")).strip().upper()
    if event_type not in VALID_SCAN_EVENTS:
        raise ValueError(f"Invalid scan event_type. Use one of: {', '.join(VALID_SCAN_EVENTS)}")

    quantity = int(float(payload.get("quantity", 1) or 1))
    quantity = max(1, quantity)
    operator = str(payload.get("operator", "Warehouse User")).strip() or "Warehouse User"
    note = str(payload.get("note", "")).strip()

    records = load_inventory_state(enrich=True)
    rec = _find_record(records, payload)
    if rec is None:
        raise ValueError("Could not match scan to an inventory item. Provide barcode or item_name + department.")

    before_stock = int(float(rec.get("current_stock", 0) or 0))
    delta = STOCK_DELTAS[event_type] * quantity
    after_stock = max(0, before_stock + delta)
    now = datetime.now().isoformat(timespec="seconds")

    rec["current_stock"] = after_stock
    rec["last_scan_at"] = now
    rec["last_scan_event"] = event_type
    if event_type == "RECALLED_REMOVED":
        rec["recall_status"] = "Recalled - Removed"

    save_inventory_state(records)

    event = {
        "event_id": f"SCAN-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": now,
        "event_type": event_type,
        "quantity": quantity,
        "operator": operator,
        "item_name": rec.get("item_name"),
        "department": rec.get("department"),
        "barcode": rec.get("barcode"),
        "udi_code": rec.get("udi_code"),
        "lot_number": rec.get("lot_number"),
        "location": rec.get("location"),
        "stock_before": before_stock,
        "stock_after": after_stock,
        "stock_delta": delta,
        "note": note,
    }
    os.makedirs(os.path.dirname(SCAN_EVENTS_PATH), exist_ok=True)
    with open(SCAN_EVENTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return event
