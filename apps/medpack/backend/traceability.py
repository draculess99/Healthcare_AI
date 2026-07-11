"""Stage 1 operational traceability helpers for MedPack AI.

Adds hospital-supply-chain fields that make the app look and behave more like a
real supply control tower: lot, UDI/barcode, expiration, location, PAR levels,
vendor identity, recall status, and cold-chain flags.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping

INVENTORY_PATH = "database/inventory_state.json"

TRACEABILITY_FIELDS = [
    "lot_number",
    "udi_code",
    "barcode",
    "expiration_date",
    "location",
    "par_level",
    "max_stock",
    "vendor_id",
    "vendor_name",
    "last_scan_at",
    "last_scan_event",
    "recall_status",
    "storage_type",
    "temperature_sensitive",
]

VENDORS = [
    ("V001", "NorthStar Medical Supply"),
    ("V002", "Beacon Hospital Logistics"),
    ("V003", "Atlas Clinical Distribution"),
    ("V004", "BlueLine MedSource"),
]

TEMP_SENSITIVE_CATEGORIES = {"Respiratory", "Lab Supplies", "Surgical Supplies"}
RECALL_CANDIDATES = {("Oxygen Mask", "ICU"), ("Surgical Tray", "Surgery")}


def _stable_int(*parts: Any) -> int:
    raw = "|".join(str(p) for p in parts)
    return int(hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8], 16)


def _normalise_dept(department: str) -> str:
    return "".join(ch for ch in department.upper() if ch.isalnum())[:8] or "GEN"


def enrich_record(record: Mapping[str, Any], index: int = 0) -> Dict[str, Any]:
    """Return a copy of an inventory record with Stage 1 fields populated.

    Existing values are preserved, so scan updates and user edits do not get
    overwritten on the next load.
    """
    enriched = dict(record)
    item = str(enriched.get("item_name", "Unknown Item"))
    dept = str(enriched.get("department", "Unknown Department"))
    category = str(enriched.get("item_category", "General"))
    seed = _stable_int(item, dept, index)

    lot_suffix = seed % 100000
    item_code = "".join(ch for ch in item.upper() if ch.isalnum())[:6] or "ITEM"
    dept_code = _normalise_dept(dept)
    vendor_id, vendor_name = VENDORS[seed % len(VENDORS)]

    current_stock = int(float(enriched.get("current_stock", 0) or 0))
    reorder_point = int(float(enriched.get("reorder_point", 20) or 20))
    recent_usage_rate = float(enriched.get("recent_usage_rate", 4.0) or 4.0)
    supplier_delay_days = float(enriched.get("supplier_delay_days", 2.0) or 2.0)
    clinical_criticality = int(float(enriched.get("clinical_criticality", 2) or 2))

    suggested_par = int(round(max(reorder_point, recent_usage_rate * max(supplier_delay_days, 1.0) * (1.1 + clinical_criticality * 0.12))))
    par_level = int(enriched.get("par_level") or max(reorder_point, suggested_par, 10))
    max_stock = int(enriched.get("max_stock") or max(par_level * 2, current_stock + par_level, 25))

    # Create varied dates: a few already expired, some within 30 days, most safe.
    # This makes the new compliance panel visibly useful on first run.
    days_offset = (seed % 420) - 25
    expiration_date = enriched.get("expiration_date")
    if not expiration_date:
        expiration_date = (datetime.now() + timedelta(days=days_offset)).date().isoformat()

    recall_status = enriched.get("recall_status")
    if not recall_status:
        recall_status = "Recalled" if (item, dept) in RECALL_CANDIDATES else "Clear"

    storage_type = enriched.get("storage_type") or ("Cold Chain" if category in TEMP_SENSITIVE_CATEGORIES and seed % 5 == 0 else "Room Temperature")
    temp_sensitive = bool(enriched.get("temperature_sensitive", storage_type == "Cold Chain"))

    enriched.setdefault("lot_number", f"LOT-{dept_code}-{lot_suffix:05d}")
    enriched.setdefault("udi_code", f"UDI-{item_code}-{dept_code}-{lot_suffix:05d}")
    enriched.setdefault("barcode", f"MEDPACK-{item_code}-{lot_suffix:05d}")
    enriched.setdefault("expiration_date", expiration_date)
    enriched.setdefault("location", f"{dept} PAR Room Bin {chr(65 + seed % 6)}{1 + seed % 9}")
    enriched.setdefault("par_level", par_level)
    enriched.setdefault("max_stock", max_stock)
    enriched.setdefault("vendor_id", vendor_id)
    enriched.setdefault("vendor_name", vendor_name)
    enriched.setdefault("last_scan_at", None)
    enriched.setdefault("last_scan_event", "Seeded Inventory Snapshot")
    enriched.setdefault("recall_status", recall_status)
    enriched.setdefault("storage_type", storage_type)
    enriched.setdefault("temperature_sensitive", temp_sensitive)
    return enriched


def enrich_inventory_records(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [enrich_record(record, index=i) for i, record in enumerate(records)]


def load_inventory_state(enrich: bool = True) -> List[Dict[str, Any]]:
    if not os.path.exists(INVENTORY_PATH):
        return []
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)
    if not isinstance(records, list):
        return []
    return enrich_inventory_records(records) if enrich else [dict(r) for r in records]


def save_inventory_state(records: Iterable[Mapping[str, Any]]) -> None:
    os.makedirs(os.path.dirname(INVENTORY_PATH), exist_ok=True)
    with open(INVENTORY_PATH, "w", encoding="utf-8") as f:
        json.dump([dict(r) for r in records], f, indent=2)


def ensure_traceability_fields() -> List[Dict[str, Any]]:
    """Persist Stage 1 fields into database/inventory_state.json."""
    records = load_inventory_state(enrich=False)
    if not records:
        return []
    enriched = enrich_inventory_records(records)
    changed = any(any(field not in r for field in TRACEABILITY_FIELDS) for r in records)
    if changed:
        save_inventory_state(enriched)
    return enriched
