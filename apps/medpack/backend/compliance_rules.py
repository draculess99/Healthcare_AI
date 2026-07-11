"""Stage 1 compliance and safety alerts for inventory records."""
from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Mapping, Optional


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None


def _summary_record(record: Mapping[str, Any], reason: str, severity: str, days_until_expiration: Optional[int] = None) -> Dict[str, Any]:
    out = {
        "item_name": record.get("item_name", "Unknown Item"),
        "department": record.get("department", "Unknown Department"),
        "item_category": record.get("item_category", "Unknown"),
        "current_stock": int(float(record.get("current_stock", 0) or 0)),
        "par_level": int(float(record.get("par_level", record.get("reorder_point", 0)) or 0)),
        "lot_number": record.get("lot_number", ""),
        "udi_code": record.get("udi_code", ""),
        "barcode": record.get("barcode", ""),
        "expiration_date": record.get("expiration_date", ""),
        "recall_status": record.get("recall_status", "Clear"),
        "location": record.get("location", ""),
        "vendor_name": record.get("vendor_name", ""),
        "storage_type": record.get("storage_type", "Room Temperature"),
        "temperature_sensitive": bool(record.get("temperature_sensitive", False)),
        "severity": severity,
        "reason": reason,
    }
    if days_until_expiration is not None:
        out["days_until_expiration"] = days_until_expiration
    return out


def build_compliance_alerts(records: Iterable[Mapping[str, Any]], department: Optional[str] = None, expiration_window_days: int = 30) -> Dict[str, Any]:
    """Build alert buckets: below PAR, expiring, expired, recalled, cold-chain."""
    today = datetime.now().date()
    filtered = [dict(r) for r in records if not department or r.get("department") == department]

    below_par: List[Dict[str, Any]] = []
    expiring_soon: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []
    recalled: List[Dict[str, Any]] = []
    temperature_sensitive: List[Dict[str, Any]] = []

    for rec in filtered:
        current_stock = int(float(rec.get("current_stock", 0) or 0))
        par_level = int(float(rec.get("par_level", rec.get("reorder_point", 0)) or 0))
        if par_level and current_stock < par_level:
            below_par.append(_summary_record(rec, f"Stock is {par_level - current_stock} units below PAR.", "High" if current_stock <= par_level * 0.5 else "Medium"))

        exp_date = _parse_date(rec.get("expiration_date"))
        if exp_date:
            days_left = (exp_date - today).days
            if days_left < 0:
                expired.append(_summary_record(rec, "Expired stock should be removed from usable supply.", "Critical", days_left))
            elif days_left <= expiration_window_days:
                expiring_soon.append(_summary_record(rec, f"Expires in {days_left} days. Use first or quarantine if policy requires.", "High" if days_left <= 7 else "Medium", days_left))

        if str(rec.get("recall_status", "Clear")).strip().lower() not in {"", "clear", "none", "no"}:
            recalled.append(_summary_record(rec, "Lot is marked recalled. Remove and escalate.", "Critical"))

        if bool(rec.get("temperature_sensitive", False)) or str(rec.get("storage_type", "")).lower() == "cold chain":
            temperature_sensitive.append(_summary_record(rec, "Temperature-sensitive stock requires controlled storage handling.", "Medium"))

    # Sort the most urgent things first.
    below_par.sort(key=lambda x: (x["severity"] == "High", x["par_level"] - x["current_stock"]), reverse=True)
    expiring_soon.sort(key=lambda x: x.get("days_until_expiration", 999))
    expired.sort(key=lambda x: x.get("days_until_expiration", 999))

    counts = {
        "below_par": len(below_par),
        "expiring_soon": len(expiring_soon),
        "expired": len(expired),
        "recalled": len(recalled),
        "temperature_sensitive": len(temperature_sensitive),
    }
    return {
        "department": department or "All Departments",
        "expiration_window_days": expiration_window_days,
        "counts": counts,
        "alerts": {
            "below_par": below_par[:50],
            "expiring_soon": expiring_soon[:50],
            "expired": expired[:50],
            "recalled": recalled[:50],
            "temperature_sensitive": temperature_sensitive[:50],
        },
        "control_tower_summary": _build_summary(counts),
    }


def _build_summary(counts: Mapping[str, int]) -> str:
    if counts.get("recalled", 0) or counts.get("expired", 0):
        return "Critical safety action required: remove recalled/expired lots before normal packing continues."
    if counts.get("below_par", 0) or counts.get("expiring_soon", 0):
        return "Operational action required: replenish below-PAR items and rotate expiring stock first."
    return "No major Stage 1 compliance exceptions detected in the selected scope."
