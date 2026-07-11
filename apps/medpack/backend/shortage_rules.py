def _threshold_summary(shortage_gap, coverage_ratio):
    """Return a precise explanation of which shortage threshold(s) were crossed."""
    crossed = []
    if shortage_gap >= 30:
        crossed.append(f"shortage gap is {shortage_gap:.1f} units, meeting the Critical gap threshold of 30+")
    elif shortage_gap >= 15:
        crossed.append(f"shortage gap is {shortage_gap:.1f} units, meeting the High gap threshold of 15+")
    elif shortage_gap >= 5:
        crossed.append(f"shortage gap is {shortage_gap:.1f} units, meeting the Medium gap threshold of 5+")

    if coverage_ratio < 0.50:
        crossed.append(f"stock coverage is {coverage_ratio * 100:.1f}%, below the Critical coverage threshold of 50%")
    elif coverage_ratio < 0.75:
        crossed.append(f"stock coverage is {coverage_ratio * 100:.1f}%, below the High coverage threshold of 75%")
    elif coverage_ratio < 1.00:
        crossed.append(f"stock coverage is {coverage_ratio * 100:.1f}%, below the Medium coverage threshold of 100%")

    return crossed


def calculate_shortage_risk(predicted_24h_demand, current_stock):
    """Convert demand forecast and inventory level into an auditable shortage-risk decision.

    Risk levels are intentionally conservative: crossing either the shortage-gap threshold
    or the coverage-ratio threshold can elevate the risk level. The explanation reports
    the exact trigger(s), avoiding misleading language when only one condition is met.
    """
    predicted_24h_demand = float(predicted_24h_demand)
    current_stock = int(current_stock)
    shortage_gap = predicted_24h_demand - current_stock
    coverage_ratio = current_stock / max(predicted_24h_demand, 1.0)
    triggers = _threshold_summary(shortage_gap, coverage_ratio)

    if shortage_gap >= 30 or coverage_ratio < 0.50:
        risk_level = "Critical"
        reasoning = "Critical risk identified because " + "; and ".join(
            [t for t in triggers if "Critical" in t]
        ) + ". Immediate replenishment/escalation review is recommended."
    elif shortage_gap >= 15 or coverage_ratio < 0.75:
        risk_level = "High"
        high_triggers = [t for t in triggers if "High" in t]
        reasoning = "High risk identified because " + "; and ".join(high_triggers) + ". Replenishment should be prioritized before bedside stockout risk increases."
    elif shortage_gap >= 5 or coverage_ratio < 1.00:
        risk_level = "Medium"
        medium_triggers = [t for t in triggers if "Medium" in t]
        reasoning = "Medium risk identified because " + "; and ".join(medium_triggers) + ". Monitor closely and prepare replenishment if demand continues rising."
    else:
        risk_level = "Low"
        reasoning = (
            f"Stock level is safe. Current stock ({current_stock}) covers "
            f"{coverage_ratio * 100:.1f}% of forecasted demand ({predicted_24h_demand:.1f} units)."
        )

    return {
        "predicted_24h_demand": round(float(predicted_24h_demand), 2),
        "current_stock": current_stock,
        "shortage_gap": round(float(shortage_gap), 2),
        "coverage_ratio": round(float(coverage_ratio), 4),
        "risk_level": risk_level,
        "reasoning": reasoning,
    }
