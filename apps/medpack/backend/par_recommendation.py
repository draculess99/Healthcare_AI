"""Dynamic PAR recommendation logic for Stage 1."""
from __future__ import annotations

from typing import Any, Dict, Mapping

CRITICALITY_BUFFER = {1: 0.10, 2: 0.20, 3: 0.30, 4: 0.40}


def recommend_par(telemetry: Mapping[str, Any]) -> Dict[str, Any]:
    predicted_demand = float(telemetry.get("predicted_24h_demand", 0) or 0)
    if predicted_demand <= 0:
        predicted_demand = float(telemetry.get("recent_usage_rate", 0) or 0) * 24.0

    current_stock = int(float(telemetry.get("current_stock", 0) or 0))
    current_par = int(float(telemetry.get("par_level", telemetry.get("reorder_point", 25)) or 25))
    supplier_delay_days = max(float(telemetry.get("supplier_delay_days", 1) or 1), 0.25)
    criticality = int(float(telemetry.get("clinical_criticality", 2) or 2))
    supplier_reliability = float(telemetry.get("supplier_reliability_score", 0.9) or 0.9)

    buffer_pct = CRITICALITY_BUFFER.get(criticality, 0.20)
    if supplier_reliability < 0.85:
        buffer_pct += 0.10
    if supplier_delay_days >= 5:
        buffer_pct += 0.10

    # Forecast is 24h. Supplier delay uses days of cover. Cap at sensible demo bounds.
    base_need = predicted_demand * supplier_delay_days
    recommended_par = int(round(base_need * (1 + buffer_pct)))
    recommended_par = max(recommended_par, current_par, 10)
    max_stock = max(recommended_par * 2, current_stock + recommended_par)

    delta = recommended_par - current_par
    action = "Keep current PAR" if delta <= 0 else f"Raise PAR by {delta} units"
    if current_stock < recommended_par:
        action += f" and replenish {recommended_par - current_stock} units"

    return {
        "item_name": telemetry.get("item_name", "Unknown Item"),
        "department": telemetry.get("department", "Unknown Department"),
        "current_stock": current_stock,
        "current_par": current_par,
        "recommended_par": recommended_par,
        "recommended_max_stock": int(max_stock),
        "par_delta": delta,
        "safety_buffer_pct": round(buffer_pct * 100, 1),
        "supplier_delay_days": supplier_delay_days,
        "supplier_reliability_score": supplier_reliability,
        "predicted_24h_demand": round(predicted_demand, 2),
        "recommended_action": action,
        "reasoning": (
            f"PAR based on predicted 24h demand ({predicted_demand:.1f}), supplier delay "
            f"({supplier_delay_days:.1f} days), clinical criticality ({criticality}/4), "
            f"and a {buffer_pct:.0%} safety buffer."
        ),
    }
