"""Deterministic command-center agents for Triage Assist AI.

These agents are intentionally rule-based. The ESI engine remains the source of
truth for safety-critical triage decisions; the agents explain, summarize, and
coordinate workflow without overriding the ESI result.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _review_text(minutes: Any) -> str:
    try:
        minutes = int(minutes)
    except Exception:
        return "Not specified"
    return "Immediate" if minutes == 0 else f"Within {minutes} minutes"


def _short_list(items: List[str], limit: int = 4) -> List[str]:
    cleaned = [str(item).strip() for item in (items or []) if str(item).strip()]
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + [f"+{len(cleaned) - limit} more"]


def safety_sentinel_agent(esi: Dict[str, Any], vitals: Dict[str, Any], notes: str = "", disease_probability: float = 0.0) -> Dict[str, Any]:
    """Return a safety review of the deterministic ESI output.

    This agent does not change the ESI level. It makes red flags, escalation,
    downgrade risk, and input-quality concerns visible for the nurse/clinician.
    """
    esi_level = _safe_int(esi.get("esi_level"), 5)
    red_flags = esi.get("red_flags") or []
    warnings = esi.get("data_quality_warnings") or []
    escalation = bool(esi.get("escalation_required")) or esi_level <= 2
    heart_rate = _safe_int(vitals.get("thalach"), 0)
    spo2 = _safe_int(vitals.get("oxygen_saturation"), 98)
    bp = _safe_int(vitals.get("trestbps"), 0)
    pain = _safe_int(vitals.get("pain_score"), 0)

    findings: List[str] = []
    if escalation:
        findings.append(f"ESI-{esi_level} requires urgent review/rooming.")
    if red_flags:
        findings.extend(_short_list(red_flags, limit=5))
    if warnings:
        findings.extend([f"Input consistency: {w}" for w in _short_list(warnings, limit=2)])
    if heart_rate >= 130:
        findings.append(f"Marked tachycardia present: HR {heart_rate}/min.")
    if spo2 < 92:
        findings.append(f"Low oxygen saturation present: SpO₂ {spo2}%.")
    if bp >= 180:
        findings.append(f"Severe hypertension present: systolic BP {bp} mm Hg.")
    if pain >= 8:
        findings.append(f"Severe pain documented: {pain}/10.")
    if not findings:
        findings.append("No ESI-1/ESI-2 red-flag trigger detected by the deterministic engine.")

    if esi_level <= 2:
        severity = "high"
        status = "Escalation watch"
        recommendation = "Keep nurse/clinician confirmation required; do not downgrade without a documented clinical reason."
    elif esi_level == 3:
        severity = "medium"
        status = "Monitor"
        recommendation = "Keep in urgent queue and reassess within target window."
    else:
        severity = "low"
        status = "Stable / fast-track check"
        recommendation = "Fast-track is reasonable if nurse agrees and no new red flags appear."

    return {
        "name": "Safety Sentinel Agent",
        "icon": "🛡️",
        "status": status,
        "severity": severity,
        "summary": f"Safety review complete: active queue recommendation is ESI-{esi_level}.",
        "findings": findings,
        "recommendation": recommendation,
        "guardrail": "The deterministic ESI engine remains the safety source of truth; this agent explains and flags risk only.",
    }


def documentation_agent(
    esi: Dict[str, Any],
    vitals: Dict[str, Any],
    notes: str = "",
    disease_probability: float = 0.0,
    model_name: str = "ML model",
) -> Dict[str, Any]:
    """Generate a concise SBAR-style documentation aid."""
    esi_level = _safe_int(esi.get("esi_level"), 5)
    chief_complaint = vitals.get("chief_complaint") or "Not specified"
    resources = esi.get("likely_resources") or []
    red_flags = esi.get("red_flags") or []
    actions = esi.get("recommended_next_actions") or []
    review = _review_text(esi.get("review_interval_minutes"))
    prob = _safe_float(disease_probability, 0.0)

    sbar = {
        "Situation": f"Patient presents with {chief_complaint}. Deterministic acuity recommendation is ESI-{esi_level}.",
        "Background": f"{model_name} cardiac-risk probability: {prob:.1%}. Arrival mode: {vitals.get('arrival_mode', 'Not specified')}. Mental status: {vitals.get('mental_status', 'Not specified')}.",
        "Assessment": "; ".join(_short_list(red_flags, limit=4)) if red_flags else "No high-risk red-flag trigger documented by the ESI engine.",
        "Recommendation": "; ".join(_short_list(actions, limit=3)) if actions else f"Manage per ESI-{esi_level} pathway and reassess {review.lower()}.",
    }

    note_lines = [
        f"ESI-{esi_level} generated for chief complaint: {chief_complaint}.",
        f"Escalation required: {'yes' if esi.get('escalation_required') else 'no'}.",
        f"Fast-track eligible: {'yes' if esi.get('fast_track_eligible') else 'no'}.",
        f"Reassessment target: {review}.",
    ]
    if resources:
        note_lines.append("Likely resources: " + ", ".join(_short_list(resources, limit=6)) + ".")
    if notes:
        note_lines.append("Nurse notes captured for clinician review.")

    return {
        "name": "Documentation Agent",
        "icon": "📝",
        "status": "SBAR ready",
        "severity": "info",
        "summary": "Generated an SBAR-style handoff and audit-friendly triage note.",
        "sbar": sbar,
        "handoff_note": " ".join(note_lines),
        "audit_summary": f"{chief_complaint} → ESI-{esi_level}; escalation={'yes' if esi.get('escalation_required') else 'no'}; reassess={review}.",
    }


def evaluation_command_agents(
    esi: Dict[str, Any],
    vitals: Dict[str, Any],
    notes: str = "",
    disease_probability: float = 0.0,
    model_name: str = "ML model",
) -> Dict[str, Any]:
    """Run the deterministic single-patient command-center agents."""
    return {
        "safety_sentinel": safety_sentinel_agent(esi, vitals, notes, disease_probability),
        "documentation": documentation_agent(esi, vitals, notes, disease_probability, model_name),
    }
