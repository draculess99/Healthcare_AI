from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from backend.expert_system import evaluate_rules
from backend.guardrails import (
    detect_prompt_injection,
    enforce_final_guardrails,
    redact_sensitive_text,
    validate_case,
)
from backend.llm_clients import generate_explanation
from backend.memory import JSONMemoryStore
from backend.model import DenialRiskModel
from backend.rag import PolicyRAG

ProgressCallback = Callable[[str, str, str], None]

PIPELINE_STAGES = [
    ("privacy", "Privacy Shield"),
    ("intake", "Intake Agent"),
    ("eligibility", "Eligibility Agent"),
    ("clinical", "Clinical Evidence Agent"),
    ("rag", "Policy RAG Agent"),
    ("model", "XGBoost Risk Agent"),
    ("debate", "Debate Committee"),
    ("guardrails", "Guardrail Sentinel"),
    ("arbiter", "Arbiter Agent"),
    ("memory", "Memory Agent"),
    ("human", "Human Review Gate"),
]


def _emit(callback: ProgressCallback | None, key: str, status: str, message: str) -> None:
    if callback:
        callback(key, status, message)


def _position(agent: str, stance: str, confidence: float, evidence: list[str], recommendation: str) -> dict[str, Any]:
    return {
        "agent": agent,
        "stance": stance,
        "confidence": round(float(confidence), 2),
        "evidence": evidence,
        "recommendation": recommendation,
    }


def run_pipeline(
    raw_case: dict[str, Any],
    provider: str = "Local Expert System",
    provider_model: str | None = None,
    progress_callback: ProgressCallback | None = None,
    persist: bool = True,
    memory_store: JSONMemoryStore | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    store = memory_store or JSONMemoryStore()

    _emit(progress_callback, "privacy", "running", "Scanning notes for sensitive data and prompt injection")
    errors = validate_case(raw_case)
    if errors:
        _emit(progress_callback, "privacy", "error", "Input validation failed")
        raise ValueError("; ".join(errors))

    case = dict(raw_case)
    redacted_notes, pii_findings = redact_sensitive_text(str(case.get("clinical_notes", "")))
    injection_matches = detect_prompt_injection(redacted_notes)
    case["clinical_notes"] = redacted_notes
    _emit(
        progress_callback,
        "privacy",
        "complete",
        f"Privacy scan complete; {len(pii_findings)} sensitive pattern(s) redacted",
    )

    _emit(progress_callback, "intake", "running", "Normalizing authorization request")
    case["case_id"] = str(case["case_id"]).strip()
    case["run_id"] = run_id
    case["processed_at"] = started_at
    _emit(progress_callback, "intake", "complete", "Request normalized and assigned a workflow run ID")

    _emit(progress_callback, "eligibility", "running", "Checking eligibility, network, and authorization requirement")
    eligibility_evidence = [
        "Eligibility confirmed" if case.get("member_eligible", True) else "Eligibility not confirmed",
        "In-network provider" if case.get("in_network", True) else "Out-of-network provider",
        "Prior authorization required" if case.get("prior_auth_required", True) else "Prior authorization may not be required",
    ]
    _emit(progress_callback, "eligibility", "complete", "; ".join(eligibility_evidence))

    _emit(progress_callback, "clinical", "running", "Executing deterministic clinical-documentation rules")
    rules = evaluate_rules(case)
    _emit(
        progress_callback,
        "clinical",
        "complete",
        f"Rules found {len(rules['blockers'])} blocker(s) and {len(rules['warnings'])} warning(s)",
    )

    _emit(progress_callback, "rag", "running", "Retrieving relevant payer-policy and documentation guidance")
    rag = PolicyRAG()
    query = " ".join([
        str(case.get("payer", "")),
        str(case.get("service_type", "")),
        str(case.get("diagnosis_group", "")),
        "urgent" if case.get("urgent") else "standard",
        "documentation medical necessity conservative therapy appeal",
    ])
    rag_results = rag.retrieve(query, top_k=4)
    _emit(progress_callback, "rag", "complete", f"Retrieved {len(rag_results)} policy evidence chunk(s)")

    _emit(progress_callback, "model", "running", "Scoring denial risk with XGBoost")
    model = DenialRiskModel()
    model_result = model.predict(case, rules["missing_document_count"])
    adjusted_probability = min(
        max(model_result["denial_probability"] + float(rules["risk_adjustment"]), 0.01),
        0.99,
    )
    model_result["raw_denial_probability"] = model_result["denial_probability"]
    model_result["denial_probability"] = round(adjusted_probability, 4)
    model_result["approval_probability"] = round(1 - adjusted_probability, 4)
    model_result["risk_level"] = (
        "Low" if adjusted_probability < 0.25
        else "Moderate" if adjusted_probability < 0.55
        else "High" if adjusted_probability < 0.80
        else "Critical"
    )
    _emit(
        progress_callback,
        "model",
        "complete",
        f"Adjusted denial risk: {adjusted_probability:.1%} ({model_result['risk_level']})",
    )

    _emit(progress_callback, "debate", "running", "Committee agents are challenging the evidence and routing proposal")
    debate: list[dict[str, Any]] = []
    debate.append(_position(
        "Coverage & Eligibility Agent",
        "SUPPORT" if case.get("member_eligible", True) and case.get("in_network", True) else "OPPOSE",
        0.94,
        eligibility_evidence,
        "Proceed" if case.get("member_eligible", True) else "Hold until eligibility is verified",
    ))
    debate.append(_position(
        "Clinical Evidence Agent",
        "SUPPORT" if not rules["blockers"] else "OPPOSE",
        0.90,
        (rules["passes"] + rules["blockers"])[:5],
        "Evidence package is sufficient" if not rules["blockers"] else "Obtain missing clinical documentation",
    ))
    debate.append(_position(
        "Policy RAG Agent",
        "CAUTION" if rag_results else "OPPOSE",
        0.78 if rag_results else 0.55,
        [f"{row['source']}: {row['text'][:180]}" for row in rag_results[:3]] or ["No matching local policy chunk found"],
        "Use retrieved guidance as a checklist; verify payer-specific current policy",
    ))
    debate.append(_position(
        "XGBoost Denial-Risk Agent",
        "OPPOSE" if adjusted_probability >= 0.55 else "SUPPORT",
        max(0.60, abs(adjusted_probability - 0.5) * 2),
        [
            f"Estimated denial probability: {adjusted_probability:.1%}",
            *[f"{row['feature']} {row['direction']}" for row in model_result["top_signals"][:3]],
        ],
        "Escalate" if adjusted_probability >= 0.55 else "Proceed with standard review",
    ))
    debate.append(_position(
        "Devil's Advocate Agent",
        "OPPOSE" if rules["warnings"] or adjusted_probability >= 0.35 else "CAUTION",
        0.82,
        (rules["warnings"] or ["Challenge whether the documentation directly proves medical necessity"])[:4],
        "Resolve the strongest counterargument before submission",
    ))
    debate.append(_position(
        "Compliance & Safety Agent",
        "OPPOSE" if injection_matches or pii_findings else "SUPPORT",
        0.99,
        [
            f"PII patterns redacted: {', '.join(pii_findings) if pii_findings else 'none'}",
            f"Prompt-injection indicators: {len(injection_matches)}",
            "LLM is explanation-only and cannot change routing",
        ],
        "Bypass LLM and require human review" if injection_matches else "Continue within deterministic guardrails",
    ))
    support = sum(1 for item in debate if item["stance"] == "SUPPORT")
    oppose = sum(1 for item in debate if item["stance"] == "OPPOSE")
    caution = len(debate) - support - oppose
    _emit(
        progress_callback,
        "debate",
        "complete",
        f"Committee vote: {support} support, {oppose} oppose, {caution} caution",
    )

    _emit(progress_callback, "guardrails", "running", "Applying non-negotiable safety and routing constraints")
    proposed = "READY_FOR_SUBMISSION_REVIEW"
    if rules["blockers"]:
        proposed = "HOLD_FOR_DOCUMENTATION"
    elif adjusted_probability >= 0.55 or oppose >= 3:
        proposed = "HUMAN_REVIEW_REQUIRED"
    decision, human_required, guardrail_reasons = enforce_final_guardrails(
        case=case,
        proposed_decision=proposed,
        denial_probability=adjusted_probability,
        blockers=rules["blockers"],
        warnings=rules["warnings"],
        injection_detected=bool(injection_matches),
    )
    _emit(progress_callback, "guardrails", "complete", f"Guardrails locked decision to {decision}")

    _emit(progress_callback, "arbiter", "running", "Arbiter is reconciling model, rules, policy evidence, and debate")
    explanation_context = {
        "decision": decision,
        "risk_level": model_result["risk_level"],
        "denial_probability": adjusted_probability,
        "blockers": rules["blockers"],
        "warnings": rules["warnings"],
        "committee_vote": {"support": support, "oppose": oppose, "caution": caution},
        "guardrail_reasons": guardrail_reasons,
    }
    llm_bypassed = bool(injection_matches)
    if llm_bypassed:
        narrative = (
            "The language safety screen detected a prompt-injection pattern. The external LLM was bypassed. "
            "The deterministic workflow isolated the case for human review."
        )
        llm_warning = None
        explanation_provider = "Guardrail-only local explanation"
        explanation_model = "guardrail-local"
        usage_dict = None
    else:
        narrative, llm_warning, explanation_model, usage_dict = generate_explanation(
            provider, explanation_context, model=provider_model
        )
        explanation_provider = provider
    _emit(progress_callback, "arbiter", "complete", "Arbiter issued an immutable routing recommendation")

    _emit(progress_callback, "memory", "running", "Searching JSON memory for similar reviewed scenarios")
    similar_cases = store.find_similar(case, limit=3)
    _emit(progress_callback, "memory", "complete", f"Found {len(similar_cases)} similar prior scenario(s)")

    _emit(progress_callback, "human", "running", "Evaluating whether qualified human action is mandatory")
    if human_required:
        review_status = "PENDING_REQUIRED_REVIEW"
        human_message = "Workflow paused for qualified utilization-management review."
    else:
        review_status = "READY_FOR_OPTIONAL_FINAL_REVIEW"
        human_message = "No mandatory escalation found; final specialist review is still recommended before submission."
    _emit(progress_callback, "human", "complete", human_message)

    result = {
        "run_id": run_id,
        "processed_at": started_at,
        "case": case,
        "privacy": {
            "pii_patterns_redacted": pii_findings,
            "prompt_injection_matches": injection_matches,
            "llm_bypassed": llm_bypassed,
        },
        "rules": rules,
        "rag_evidence": rag_results,
        "model": model_result,
        "debate": debate,
        "committee_vote": {"support": support, "oppose": oppose, "caution": caution},
        "decision": decision,
        "human_review_required": human_required,
        "review_status": review_status,
        "guardrail_reasons": guardrail_reasons,
        "narrative": narrative,
        "explanation_provider": explanation_provider,
        "explanation_model": explanation_model,
        "token_usage": usage_dict,
        "data_source": case.get("data_source", "manual_or_synthetic"),
        "llm_warning": llm_warning,
        "similar_cases": similar_cases,
        "pipeline": [
            {"key": key, "label": label, "status": "complete"}
            for key, label in PIPELINE_STAGES
        ],
        "disclaimer": (
            "Educational portfolio prototype using synthetic/proxy data. It does not determine coverage, provide medical advice, "
            "or submit prior authorizations. Qualified personnel must verify current payer policy and clinical evidence."
        ),
    }

    if persist:
        store.append_case(result)
        store.append_memory({
            "run_id": run_id,
            "case_id": case["case_id"],
            "payer": case.get("payer"),
            "service_type": case.get("service_type"),
            "diagnosis_group": case.get("diagnosis_group"),
            "urgent": bool(case.get("urgent")),
            "decision": decision,
            "risk_level": model_result["risk_level"],
            "denial_probability": adjusted_probability,
            "blocker_count": len(rules["blockers"]),
            "created_at": started_at,
        })
    return result
