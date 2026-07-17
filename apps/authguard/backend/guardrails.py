from __future__ import annotations

import re
from typing import Any

PII_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "phone": re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)"),
}

INJECTION_PHRASES = (
    "ignore previous instructions",
    "ignore all rules",
    "bypass guardrails",
    "override the policy",
    "reveal system prompt",
    "auto approve regardless",
    "do not send to human",
    "pretend this is approved",
)


def redact_sensitive_text(text: str) -> tuple[str, list[str]]:
    redacted = text or ""
    findings: list[str] = []
    for label, pattern in PII_PATTERNS.items():
        if pattern.search(redacted):
            findings.append(label)
            redacted = pattern.sub(f"[REDACTED_{label.upper()}]", redacted)
    return redacted, findings


def detect_prompt_injection(text: str) -> list[str]:
    lower = (text or "").lower()
    return [phrase for phrase in INJECTION_PHRASES if phrase in lower]


def validate_case(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ["case_id", "payer", "service_type", "diagnosis_group"]
    for field in required:
        value = case.get(field)
        if value is None or not str(value).strip():
            errors.append(f"{field} is required")

    numeric_ranges = {
        "age_years": (0, 120),
        "requested_units": (1, 365),
        "evidence_count": (0, 50),
        "required_document_count": (0, 50),
        "conservative_therapy_weeks": (0, 104),
        "guideline_min_weeks": (0, 104),
        "estimated_cost": (0, 10_000_000),
        "previous_denials": (0, 20),
    }
    for field, (low, high) in numeric_ranges.items():
        try:
            value = float(case.get(field, 0))
            if not low <= value <= high:
                errors.append(f"{field} must be between {low} and {high}")
        except (TypeError, ValueError):
            errors.append(f"{field} must be numeric")
    return errors


def enforce_final_guardrails(
    case: dict[str, Any],
    proposed_decision: str,
    denial_probability: float,
    blockers: list[str],
    warnings: list[str],
    injection_detected: bool,
) -> tuple[str, bool, list[str]]:
    """Guardrails may only make a decision stricter, never more permissive."""
    reasons: list[str] = []
    decision = proposed_decision
    human_required = proposed_decision in {
        "HUMAN_REVIEW_REQUIRED",
        "URGENT_HUMAN_REVIEW",
        "ESCALATE_DENIAL_RISK",
        "HOLD_ELIGIBILITY",
        "HOLD_FOR_DOCUMENTATION",
    }
    if human_required:
        reasons.append("The proposed route requires a qualified human reviewer before the workflow can proceed.")

    if injection_detected:
        return (
            "HUMAN_REVIEW_REQUIRED",
            True,
            ["Prompt-injection language detected; LLM bypassed and case isolated."],
        )

    if not bool(case.get("member_eligible", True)):
        decision = "HOLD_ELIGIBILITY"
        human_required = True
        reasons.append("Member eligibility is not confirmed.")

    if blockers:
        decision = "HOLD_FOR_DOCUMENTATION"
        human_required = True
        reasons.append("Blocking documentation or policy requirements remain unresolved.")

    if bool(case.get("urgent")):
        decision = "URGENT_HUMAN_REVIEW"
        human_required = True
        reasons.append("Urgent request requires expedited human utilization-management review.")

    if denial_probability >= 0.80:
        decision = "ESCALATE_DENIAL_RISK"
        human_required = True
        reasons.append("Model-estimated denial risk is critical (>= 80%).")
    elif denial_probability >= 0.55 and decision == "READY_FOR_SUBMISSION_REVIEW":
        decision = "HUMAN_REVIEW_REQUIRED"
        human_required = True
        reasons.append("Model-estimated denial risk is high (>= 55%).")

    if warnings and decision == "READY_FOR_SUBMISSION_REVIEW":
        decision = "HUMAN_REVIEW_REQUIRED"
        human_required = True
        reasons.append("One or more non-blocking policy warnings need review.")

    # The prototype never actually transmits a request to a payer.
    if decision == "READY_FOR_SUBMISSION_REVIEW":
        reasons.append("Package appears ready for a qualified authorization specialist to review and submit.")

    return decision, human_required, reasons
