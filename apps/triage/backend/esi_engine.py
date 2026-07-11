"""
ESI-style emergency acuity engine for Triage Assist AI.

This is a deterministic decision-support layer inspired by the Emergency
Severity Index (ESI) workflow. It is intentionally conservative for demo use:
red flags and unstable vitals override the ML probability so dangerous cases
are escalated even when the heart-disease model is uncertain.

Important: this is an educational prototype, not a validated clinical device.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


ESI_LABELS = {
    1: "ESI-1 — Immediate Life-Saving Intervention",
    2: "ESI-2 — Emergent / High Risk",
    3: "ESI-3 — Urgent / Multiple Resources",
    4: "ESI-4 — Less Urgent / One Resource",
    5: "ESI-5 — Non-Urgent / No Resources",
}

ESI_URGENCY = {
    1: "Immediate resuscitation / clinician at bedside now",
    2: "Immediate rooming and urgent clinician review",
    3: "Urgent ED evaluation; monitor while waiting",
    4: "Fast-track candidate if stable",
    5: "Low-acuity fast-track / self-care education candidate",
}

REVIEW_INTERVAL_MINUTES = {
    1: 0,
    2: 0,
    3: 30,
    4: 60,
    5: 120,
}

PRIORITY_SCORE_BY_ESI = {
    1: 10.0,
    2: 8.5,
    3: 6.0,
    4: 3.5,
    5: 1.5,
}

# Terms that confirm an active cardiac/chest-pain triage complaint.
# The legacy ML chest-pain feature alone must not trigger ESI chest-pain escalation,
# because it is a model feature and can conflict with the nurse's actual chief complaint.
CHEST_PAIN_TERMS = [
    "chest pain",
    "chest pressure",
    "crushing chest",
    "angina",
    "heart attack",
    "myocardial infarction",
    "cardiac symptoms",
    "cardiac complaint",
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    cleaned: List[str] = []
    for item in items:
        item = str(item).strip()
        if item and item not in seen:
            cleaned.append(item)
            seen.add(item)
    return cleaned


def infer_resources(chief_complaint: str, notes: str, selected_resources: List[str]) -> List[str]:
    """Infer likely ED resources when the user has not selected them."""
    complaint = _lower(chief_complaint)
    combined = f"{complaint} {_lower(notes)}"
    resources = list(selected_resources or [])

    if _contains_any(combined, CHEST_PAIN_TERMS):
        resources += ["ECG", "Troponin / cardiac labs", "Chest X-ray", "Serial monitoring"]
    if _contains_any(combined, ["shortness", "sob", "breath", "wheez", "asthma", "copd", "hypoxia"]):
        resources += ["Pulse-ox monitoring", "Chest X-ray", "Respiratory treatment", "Labs"]
    if _contains_any(combined, ["stroke", "face droop", "weakness", "slurred", "speech", "neuro"]):
        resources += ["Stroke screen", "CT / imaging", "Labs", "Neurology consult"]
    if _contains_any(combined, ["sepsis", "fever", "infection", "pneumonia", "uti"]):
        resources += ["Sepsis screen", "Labs", "Cultures", "IV fluids/meds"]
    if _contains_any(combined, ["trauma", "fall", "mvc", "accident", "head injury", "fracture"]):
        resources += ["Imaging", "Wound/procedure care", "Pain control"]
    if _contains_any(combined, ["abdominal", "belly", "append", "vomit", "nausea"]):
        resources += ["Labs", "Imaging", "IV fluids/meds"]
    if _contains_any(combined, ["allergic", "anaphyl", "swelling", "hives"]):
        resources += ["Airway assessment", "Medication treatment", "Observation"]
    if _contains_any(combined, ["suicidal", "homicidal", "psych", "overdose"]):
        resources += ["Safety watch", "Behavioral health consult", "Labs/toxicology"]
    if _contains_any(combined, ["laceration", "cut"]):
        resources += ["Wound/procedure care"]
    elif _contains_any(combined, ["sprain", "ankle", "wrist", "minor injury"]):
        resources += ["X-ray"]

    return _dedupe(resources)


def assess_esi_acuity(vitals: Dict[str, Any], notes: str = "", disease_probability: float = 0.0) -> Dict[str, Any]:
    """Return a conservative ESI-style acuity assessment."""
    age = _safe_int(vitals.get("age"), 0)
    systolic_bp = _safe_int(vitals.get("trestbps"), 0)
    heart_rate = _safe_int(vitals.get("thalach"), 0)
    respiratory_rate = _safe_int(vitals.get("respiratory_rate"), 16)
    oxygen_saturation = _safe_int(vitals.get("oxygen_saturation"), 98)
    temperature_f = _safe_float(vitals.get("temperature_f"), 98.6)
    pain_score = _safe_int(vitals.get("pain_score"), 0)
    cp = _safe_int(vitals.get("cp"), 4)

    chief_complaint = str(vitals.get("chief_complaint", "") or "")
    mental_status = str(vitals.get("mental_status", "Alert") or "Alert")
    arrival_mode = str(vitals.get("arrival_mode", "Walk-in") or "Walk-in")
    selected_resources = vitals.get("expected_resources", []) or []
    if isinstance(selected_resources, str):
        selected_resources = [selected_resources]

    notes_l = _lower(notes)
    complaint_l = _lower(chief_complaint)
    combined = f"{complaint_l} {notes_l}"
    active_chest_pain = bool(vitals.get("active_chest_pain", False)) or _contains_any(combined, CHEST_PAIN_TERMS)
    legacy_cp_conflict = cp in (1, 2) and not active_chest_pain

    immunocompromised = bool(vitals.get("immunocompromised", False))
    pregnant = bool(vitals.get("pregnant", False))
    anticoagulants = bool(vitals.get("anticoagulants", False))
    suicidal_homicidal = bool(vitals.get("suicidal_homicidal", False))
    can_walk = bool(vitals.get("can_walk", True))

    likely_resources = infer_resources(chief_complaint, notes, selected_resources)
    resource_count = len(likely_resources)

    red_flags: List[str] = []
    rationale: List[str] = []
    next_actions: List[str] = []
    data_quality_warnings: List[str] = []
    possible_sepsis = False

    if legacy_cp_conflict:
        data_quality_warnings.append(
            "Legacy cardiac ML chest-pain feature suggests angina, but the chief complaint/notes do not confirm active chest pain. "
            "ESI chest-pain escalation was not triggered from the ML feature alone."
        )

    # ESI-1: unstable / immediate life-saving intervention likely.
    if _lower(mental_status) in {"unresponsive", "pain only", "voice/pain only"}:
        red_flags.append("Unresponsive or only responds to voice/pain")
    if systolic_bp and systolic_bp < 90:
        red_flags.append(f"Hypotension: systolic BP {systolic_bp} mm Hg")
    if oxygen_saturation and oxygen_saturation < 90:
        red_flags.append(f"Severe hypoxia: SpO₂ {oxygen_saturation}%")
    if respiratory_rate and (respiratory_rate <= 8 or respiratory_rate >= 40):
        red_flags.append(f"Danger respiratory rate: {respiratory_rate}/min")
    if heart_rate and heart_rate > 150:
        red_flags.append(f"Extreme tachycardia: HR {heart_rate}/min")
    if _contains_any(combined, ["cardiac arrest", "not breathing", "agonal", "intubation", "massive bleeding", "active seizure"]):
        red_flags.append("Immediate life-threat language found in notes/complaint")

    esi_level = 5
    if red_flags:
        esi_level = 1
        rationale.append("Immediate instability / life-saving intervention trigger present.")
        next_actions += [
            "Move patient to resuscitation/critical care area now",
            "Notify ED provider/charge nurse immediately",
            "Start ABC assessment and continuous monitoring",
        ]
    else:
        high_risk_reasons: List[str] = []

        # ESI-2: high-risk presentations even if currently stable.
        # Chest-pain escalation requires an active cardiac chief complaint, notes, or checkbox.
        # The legacy ML cp value is intentionally not enough by itself.
        chest_pain_like = active_chest_pain
        if chest_pain_like and (age >= 40 or disease_probability >= 0.35):
            high_risk_reasons.append("Active chest-pain/cardiac complaint with elevated age or ML cardiac risk")
        if _contains_any(combined, ["stroke", "face droop", "arm weakness", "slurred", "speech", "last known well"]):
            high_risk_reasons.append("Possible stroke / time-sensitive neurologic complaint")
        if _contains_any(combined, ["anaphyl", "airway swelling", "tongue swelling", "throat swelling"]):
            high_risk_reasons.append("Possible anaphylaxis or airway compromise")
        if _contains_any(combined, ["severe shortness", "respiratory distress", "cannot breathe"]):
            high_risk_reasons.append("Severe respiratory distress described")
        if oxygen_saturation and oxygen_saturation < 92:
            high_risk_reasons.append(f"Low oxygen saturation: SpO₂ {oxygen_saturation}%")
        if systolic_bp and systolic_bp >= 180:
            high_risk_reasons.append(f"Severe hypertension: systolic BP {systolic_bp} mm Hg")
        if respiratory_rate and respiratory_rate >= 30:
            high_risk_reasons.append(f"Marked tachypnea: RR {respiratory_rate}/min")
        if heart_rate and heart_rate >= 130:
            high_risk_reasons.append(f"Marked tachycardia: HR {heart_rate}/min")
        if pain_score >= 8:
            high_risk_reasons.append(f"Severe pain score: {pain_score}/10")
        if _lower(mental_status) in {"confused/altered", "altered", "confused"}:
            high_risk_reasons.append("Altered mental status")
        if suicidal_homicidal or _contains_any(combined, ["suicidal", "homicidal", "self harm", "overdose"]):
            high_risk_reasons.append("Safety risk / suicidal, homicidal, or overdose concern")
        if _contains_any(combined, ["major trauma", "mvc", "motor vehicle", "stab", "gunshot"]):
            high_risk_reasons.append("High-risk trauma mechanism")
        if anticoagulants and _contains_any(combined, ["fall", "head", "trauma", "injury"]):
            high_risk_reasons.append("Head/trauma concern while on anticoagulants")
        if pregnant and _contains_any(combined, ["abdominal pain", "bleeding", "trauma", "syncope"]):
            high_risk_reasons.append("Pregnancy with high-risk complaint")
        if immunocompromised and (temperature_f >= 100.4 or temperature_f <= 95.0):
            high_risk_reasons.append("Immunocompromised with abnormal temperature")

        possible_sepsis = (
            _contains_any(combined, ["sepsis", "infection", "fever", "pneumonia", "uti"]) and
            ((temperature_f >= 100.4 or temperature_f <= 95.0) and (heart_rate >= 100 or respiratory_rate >= 22 or (systolic_bp and systolic_bp < 100)))
        )
        if possible_sepsis:
            high_risk_reasons.append("Possible sepsis pattern: infection concern plus abnormal vitals")

        if high_risk_reasons:
            esi_level = 2
            red_flags.extend(high_risk_reasons)
            rationale.append("High-risk presentation requires immediate rooming/clinician review.")
            next_actions += [
                "Room patient urgently / notify clinician",
                "Apply focused protocol based on complaint",
                "Begin monitoring and reassess if condition changes",
            ]
        elif resource_count >= 2 or (chest_pain_like and disease_probability >= 0.45):
            esi_level = 3
            rationale.append("Stable but likely needs two or more ED resources, or confirmed cardiac-context ML risk is moderate/high.")
            next_actions += [
                "Place in urgent queue and monitor while waiting",
                "Prepare likely diagnostic resources",
                "Reassess vital signs within 30 minutes or sooner if symptoms worsen",
            ]
        elif resource_count == 1:
            esi_level = 4
            rationale.append("Stable presentation likely needing one ED resource.")
            next_actions += [
                "Fast-track if bed/staffing allows",
                "Provide one-resource pathway and routine reassessment",
            ]
        else:
            esi_level = 5
            rationale.append("Stable presentation with no obvious ED resource requirement.")
            next_actions += [
                "Low-acuity fast-track if appropriate",
                "Provide discharge/self-care guidance only after clinician review",
            ]

    if not can_walk and esi_level > 3:
        esi_level = 3
        rationale.append("Mobility limitation upgrades acuity to at least ESI-3 for safe handling/assessment.")

    fast_track_eligible = esi_level >= 4 and not red_flags
    escalation_required = esi_level <= 2
    review_interval = REVIEW_INTERVAL_MINUTES[esi_level]
    ml_priority = round(float(disease_probability or 0.0) * 10, 1) if active_chest_pain else 0.0
    priority_score = max(PRIORITY_SCORE_BY_ESI[esi_level], ml_priority)

    # Add complaint-specific protocol hints.
    if active_chest_pain:
        next_actions.append("Chest-pain pathway: ECG/troponin consideration per local protocol")
    if _contains_any(combined, ["stroke", "face droop", "slurred", "speech"]):
        next_actions.append("Stroke pathway: document last-known-well and activate local stroke process if indicated")
    if possible_sepsis:
        next_actions.append("Sepsis pathway: prompt clinician review and sepsis screen per local protocol")

    return {
        "esi_level": esi_level,
        "esi_label": ESI_LABELS[esi_level],
        "urgency": ESI_URGENCY[esi_level],
        "priority_score": round(priority_score, 1),
        "review_interval_minutes": review_interval,
        "escalation_required": escalation_required,
        "fast_track_eligible": fast_track_eligible,
        "red_flags": _dedupe(red_flags),
        "rationale": _dedupe(rationale),
        "likely_resources": likely_resources,
        "resource_count": resource_count,
        "recommended_next_actions": _dedupe(next_actions),
        "data_quality_warnings": _dedupe(data_quality_warnings),
        "human_override_required": True,
        "source": "Deterministic ESI-style acuity engine + cardiac ML overlay only when active cardiac context is confirmed",
    }


def format_esi_markdown(esi: Dict[str, Any]) -> str:
    """Format the ESI assessment for Streamlit/LLM reports."""
    escalation = "YES — escalate now" if esi.get("escalation_required") else "No immediate escalation trigger"
    fast_track = "YES" if esi.get("fast_track_eligible") else "NO"
    review = esi.get("review_interval_minutes")
    review_text = "Immediate" if review == 0 else f"Within {review} minutes"

    lines = [
        "## 🚦 ESI-Style Acuity / Priority Engine",
        f"- **Recommended Acuity:** **{esi.get('esi_label')}**",
        f"- **Clinical Priority Score:** **{esi.get('priority_score')}/10**",
        f"- **Urgency:** {esi.get('urgency')}",
        f"- **Escalation Required:** **{escalation}**",
        f"- **Fast Track Eligible:** **{fast_track}**",
        f"- **Recommended Reassessment:** {review_text}",
    ]

    red_flags = esi.get("red_flags") or []
    if red_flags:
        lines.append("\n**Red Flags / Upgrade Triggers:**")
        lines.extend([f"- {item}" for item in red_flags])

    warnings = esi.get("data_quality_warnings") or []
    if warnings:
        lines.append("\n**Input Consistency Notes:**")
        lines.extend([f"- {item}" for item in warnings])

    resources = esi.get("likely_resources") or []
    if resources:
        lines.append("\n**Likely ED Resources:**")
        lines.extend([f"- {item}" for item in resources])

    rationale = esi.get("rationale") or []
    if rationale:
        lines.append("\n**Why this acuity was selected:**")
        lines.extend([f"- {item}" for item in rationale])

    actions = esi.get("recommended_next_actions") or []
    if actions:
        lines.append("\n**Recommended Next Actions:**")
        lines.extend([f"- {item}" for item in actions])

    lines.append("\n*Safety note: This is a demo decision-support layer. A licensed clinician must confirm or override the recommendation.*")
    return "\n".join(lines)
