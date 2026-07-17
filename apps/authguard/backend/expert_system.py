from __future__ import annotations

from typing import Any


def evaluate_rules(case: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    passes: list[str] = []
    score_adjustment = 0.0

    if not case.get("prior_auth_required", True):
        passes.append("Payer configuration indicates prior authorization may not be required; verify benefit details.")
        score_adjustment -= 0.15

    if case.get("member_eligible", True):
        passes.append("Member eligibility is confirmed.")
    else:
        blockers.append("Member eligibility is not confirmed.")
        score_adjustment += 0.35

    if case.get("in_network", True):
        passes.append("Requested provider is in network.")
    else:
        warnings.append("Requested provider is out of network; network exception or redirection may be required.")
        score_adjustment += 0.18

    required_docs = int(case.get("required_document_count", 0))
    evidence = int(case.get("evidence_count", 0))
    missing_docs = max(required_docs - evidence, 0)
    if missing_docs:
        blockers.append(f"{missing_docs} required documentation item(s) appear to be missing.")
        score_adjustment += min(0.08 * missing_docs, 0.32)
    else:
        passes.append("Required documentation count is satisfied.")

    therapy = float(case.get("conservative_therapy_weeks", 0))
    minimum = float(case.get("guideline_min_weeks", 0))
    failed = bool(case.get("failed_conservative_therapy", False))
    if minimum > 0 and therapy < minimum:
        blockers.append(
            f"Conservative therapy duration is {therapy:g} weeks; policy threshold is {minimum:g} weeks."
        )
        score_adjustment += 0.24
    elif minimum > 0 and not failed:
        warnings.append("Required conservative therapy is documented, but failure/intolerance is not confirmed.")
        score_adjustment += 0.12
    elif minimum > 0:
        passes.append("Conservative therapy threshold and failure documentation are satisfied.")

    if case.get("specialist_order", False):
        passes.append("Specialist order is present.")
    else:
        warnings.append("Specialist order is not documented.")
        score_adjustment += 0.10

    if float(case.get("estimated_cost", 0)) >= 25_000:
        warnings.append("High-cost request requires enhanced financial and medical-necessity review.")
        score_adjustment += 0.12

    if int(case.get("previous_denials", 0)) > 0:
        warnings.append("Prior denial history increases the need for a complete evidence package.")
        score_adjustment += min(0.06 * int(case.get("previous_denials", 0)), 0.18)

    if bool(case.get("urgent")):
        warnings.append("Expedited timeframe requested; confirm payer-specific urgent criteria and clock.")
        score_adjustment += 0.07

    return {
        "blockers": blockers,
        "warnings": warnings,
        "passes": passes,
        "missing_document_count": missing_docs,
        "risk_adjustment": round(score_adjustment, 4),
    }
