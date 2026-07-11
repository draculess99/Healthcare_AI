import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
from html import escape

try:
    from backend.esi_engine import assess_esi_acuity
except Exception as e:
    st.error(f"Failed to import backend.esi_engine: {e}")
    assess_esi_acuity = None

API_URL = os.getenv("TRIAGE_API_URL", "http://127.0.0.1:5103/api").rstrip("/")

st.set_page_config(page_title="Triage Assist AI", layout="wide")

st.markdown("""
<style>
    .main-hero {
        padding: 1.1rem 1.25rem;
        border-radius: 18px;
        border: 1px solid rgba(56, 189, 248, 0.35);
        background: linear-gradient(135deg, rgba(15,23,42,0.95), rgba(30,41,59,0.92));
        box-shadow: 0 8px 28px rgba(2, 6, 23, 0.18);
        margin-bottom: 1rem;
    }
    .hero-title {
        font-size: 2.1rem;
        font-weight: 800;
        margin: 0 0 .25rem 0;
        color: #e2e8f0;
    }
    .hero-subtitle {
        font-size: 1rem;
        color: #cbd5e1;
        margin-bottom: .9rem;
    }
    .badge-row {
        display: flex;
        flex-wrap: wrap;
        gap: .5rem;
    }
    .protocol-badge {
        padding: .35rem .65rem;
        border-radius: 999px;
        background: rgba(14, 165, 233, 0.16);
        border: 1px solid rgba(14, 165, 233, 0.35);
        color: #e0f2fe;
        font-size: .85rem;
        font-weight: 700;
    }
    .esi-card {
        padding: 1.15rem;
        border-radius: 18px;
        margin: .5rem 0 1rem 0;
        border: 1px solid rgba(148, 163, 184, 0.32);
        background: rgba(15, 23, 42, 0.04);
    }
    .esi-critical {
        border-left: 10px solid #ef4444;
        background: rgba(239, 68, 68, 0.08);
    }
    .esi-emergent {
        border-left: 10px solid #f97316;
        background: rgba(249, 115, 22, 0.08);
    }
    .esi-urgent {
        border-left: 10px solid #eab308;
        background: rgba(234, 179, 8, 0.08);
    }
    .esi-low {
        border-left: 10px solid #22c55e;
        background: rgba(34, 197, 94, 0.08);
    }
    .esi-level {
        font-size: 3.2rem;
        line-height: 1;
        font-weight: 900;
        margin-bottom: .25rem;
    }
    .esi-label {
        font-size: 1.15rem;
        font-weight: 800;
        margin-bottom: .35rem;
    }
    .esi-small {
        color: #64748b;
        font-size: .95rem;
    }
    .action-chip {
        display: inline-block;
        padding: .25rem .55rem;
        margin: .15rem .2rem .15rem 0;
        border-radius: .65rem;
        background: rgba(15, 23, 42, .08);
        border: 1px solid rgba(15, 23, 42, .12);
        font-size: .84rem;
    }
    .override-box {
        border: 1px dashed rgba(148, 163, 184, 0.75);
        border-radius: 16px;
        padding: 1rem;
        background: rgba(148, 163, 184, 0.08);
        margin-top: .75rem;
    }

    .queue-note {
        padding: .65rem .8rem;
        border-radius: 12px;
        background: rgba(14, 165, 233, 0.08);
        border: 1px solid rgba(14, 165, 233, 0.25);
        margin: .5rem 0 1rem 0;
        font-size: .92rem;
    }

    .result-panel {
        padding: 1.1rem 1.2rem;
        border-radius: 18px;
        border: 2px solid rgba(14, 165, 233, 0.55);
        background: linear-gradient(135deg, rgba(14, 165, 233, 0.12), rgba(15, 23, 42, 0.03));
        box-shadow: 0 8px 24px rgba(2, 6, 23, 0.10);
        margin: 1.15rem 0 .85rem 0;
    }
    .result-kicker {
        color: #38bdf8;
        font-size: .82rem;
        font-weight: 900;
        letter-spacing: .06em;
        text-transform: uppercase;
        margin-bottom: .25rem;
    }
    .result-title {
        font-size: 1.35rem;
        font-weight: 900;
        color: #f8fafc;
        margin-bottom: .35rem;
    }
    .result-subtitle {
        color: #cbd5e1;
        font-size: .95rem;
        margin-bottom: .75rem;
    }
    .result-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: .55rem;
        margin-top: .7rem;
    }
    .result-tile {
        border-radius: 14px;
        border: 1px solid rgba(14, 165, 233, 0.35);
        background: rgba(15, 23, 42, 0.78);
        padding: .65rem .75rem;
    }
    .result-tile-label {
        color: #93c5fd;
        font-size: .72rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: .04em;
    }
    .result-tile-value {
        color: #f8fafc;
        font-size: 1rem;
        font-weight: 900;
        margin-top: .15rem;
    }
    .result-help {
        padding: .55rem .75rem;
        border-radius: 12px;
        background: rgba(22, 163, 74, 0.24);
        border: 1px solid rgba(34, 197, 94, 0.55);
        color: #dcfce7;
        font-size: .92rem;
        margin-top: .65rem;
        font-weight: 800;
    }
    .reset-note {
        padding: .55rem .75rem;
        border-radius: 12px;
        background: rgba(59, 130, 246, 0.16);
        border: 1px solid rgba(96, 165, 250, 0.45);
        color: #dbeafe;
        font-size: .9rem;
        margin-top: .6rem;
    }
    .timing-help {
        padding: .55rem .75rem;
        border-radius: 12px;
        background: rgba(234, 179, 8, 0.10);
        border: 1px solid rgba(234, 179, 8, 0.35);
        color: #fef3c7;
        font-size: .9rem;
        margin: .5rem 0 .75rem 0;
    }
    .reassessment-panel {
        padding: .85rem 1rem;
        border-radius: 16px;
        background: rgba(30, 41, 59, 0.72);
        border: 1px solid rgba(125, 211, 252, 0.35);
        margin: .75rem 0;
    }
    .deterioration-banner {
        padding: .65rem .8rem;
        border-radius: 12px;
        background: rgba(239, 68, 68, 0.18);
        border: 1px solid rgba(248, 113, 113, 0.55);
        color: #fee2e2;
        font-weight: 800;
        margin: .55rem 0;
    }
    .stable-banner {
        padding: .65rem .8rem;
        border-radius: 12px;
        background: rgba(34, 197, 94, 0.18);
        border: 1px solid rgba(74, 222, 128, 0.55);
        color: #dcfce7;
        font-weight: 800;
        margin: .55rem 0;
    }

    .safety-warning {
        padding: .65rem .8rem;
        border-radius: 12px;
        background: rgba(234, 179, 8, 0.20);
        border: 1px solid rgba(251, 191, 36, 0.70);
        color: #fef3c7;
        font-weight: 800;
        margin: .55rem 0;
    }
    .timeline-box {
        padding: .65rem .8rem;
        border-radius: 12px;
        background: rgba(15, 23, 42, 0.55);
        border: 1px solid rgba(148, 163, 184, 0.35);
        margin: .55rem 0;
    }

    .agent-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
        gap: .75rem;
        margin: .75rem 0 1rem 0;
    }
    .agent-card {
        border-radius: 16px;
        border: 1px solid rgba(125, 211, 252, 0.34);
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.86), rgba(30, 41, 59, 0.76));
        padding: .85rem .95rem;
        box-shadow: 0 6px 18px rgba(2, 6, 23, 0.12);
    }
    .agent-card-high {
        border-color: rgba(248, 113, 113, 0.74);
        background: linear-gradient(135deg, rgba(127, 29, 29, 0.58), rgba(30, 41, 59, 0.76));
    }
    .agent-card-medium {
        border-color: rgba(251, 191, 36, 0.70);
        background: linear-gradient(135deg, rgba(113, 63, 18, 0.52), rgba(30, 41, 59, 0.76));
    }
    .agent-card-low {
        border-color: rgba(74, 222, 128, 0.58);
        background: linear-gradient(135deg, rgba(20, 83, 45, 0.46), rgba(30, 41, 59, 0.76));
    }
    .agent-kicker {
        color: #93c5fd;
        font-size: .72rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .05em;
        margin-bottom: .2rem;
    }
    .agent-title {
        color: #f8fafc;
        font-size: 1.02rem;
        font-weight: 900;
        margin-bottom: .25rem;
    }
    .agent-status {
        display: inline-block;
        padding: .18rem .45rem;
        border-radius: 999px;
        color: #e0f2fe;
        background: rgba(14, 165, 233, 0.18);
        border: 1px solid rgba(14, 165, 233, 0.35);
        font-weight: 800;
        font-size: .76rem;
        margin-bottom: .35rem;
    }
    .agent-summary {
        color: #e2e8f0;
        font-size: .88rem;
        line-height: 1.35;
        margin: .35rem 0;
    }
    .agent-list {
        color: #cbd5e1;
        font-size: .82rem;
        margin: .35rem 0 0 0;
        padding-left: 1.05rem;
    }

    div[data-testid="stAlert"] p,
    div[data-testid="stAlert"] div {
        color: #f8fafc !important;
    }
</style>
""", unsafe_allow_html=True)


def render_header():
    st.markdown(
        """
        <div class="main-hero">
            <div class="hero-title">🏥 Triage Assist AI — ED Command Center</div>
            <div class="hero-subtitle">
                Deterministic ESI-style acuity engine + ML cardiac-risk overlay + agentic clinical handoff.
            </div>
            <div class="badge-row">
                <span class="protocol-badge">🚦 ESI 1–5 Acuity</span>
                <span class="protocol-badge">🚨 Red-Flag Escalation</span>
                <span class="protocol-badge">🧪 Resource Prediction</span>
                <span class="protocol-badge">⚡ Fast-Track Gate</span>
                <span class="protocol-badge">👩‍⚕️ Nurse Override Audit</span>
                <span class="protocol-badge">🤖 Command Agents</span>
                <span class="protocol-badge">🔁 Reassessment Timer</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _esi_visual_class(level):
    try:
        level = int(level)
    except Exception:
        return "esi-low"
    if level == 1:
        return "esi-critical"
    if level == 2:
        return "esi-emergent"
    if level == 3:
        return "esi-urgent"
    return "esi-low"


def _review_text(review):
    return "Immediate" if review == 0 else f"{review} min"


def render_esi_card(esi, compact=False):
    """Render the ESI-style result as a command-center card."""
    if not esi:
        st.info("Run an evaluation to activate the ESI acuity card.")
        return

    esi_level = esi.get("esi_level", "-")
    esi_label = esi.get("esi_label", f"ESI-{esi_level}")
    escalation_required = esi.get("escalation_required", False)
    fast_track = esi.get("fast_track_eligible", False)
    review = esi.get("review_interval_minutes", "-")
    visual_class = _esi_visual_class(esi_level)

    st.markdown(
        f"""
        <div class="esi-card {visual_class}">
            <div class="esi-level">ESI-{esi_level}</div>
            <div class="esi-label">{esi_label}</div>
            <div class="esi-small">{esi.get('urgency', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Priority Score", f"{esi.get('priority_score', '-')}/10")
    c2.metric("Escalation", "YES" if escalation_required else "No")
    c3.metric("Reassessment", _review_text(review))
    c4.metric("Fast Track", "Yes" if fast_track else "No")

    if escalation_required:
        st.error(f"🚨 **Escalation Required:** {esi.get('urgency', 'Immediate clinician review required')}")
    elif int(esi_level) == 3:
        st.warning(f"⚠️ **Urgent:** {esi.get('urgency', 'Monitor while waiting')}")
    else:
        st.success(f"✅ **Lower Acuity / Stable:** {esi.get('urgency', 'Fast-track if appropriate')}")

    red_flags = esi.get("red_flags", [])
    rationale = esi.get("rationale", [])
    resources = esi.get("likely_resources", [])
    actions = esi.get("recommended_next_actions", [])
    data_quality_warnings = esi.get("data_quality_warnings", [])

    if red_flags:
        st.markdown("**🚨 Red flags / upgrade triggers**")
        for item in red_flags:
            st.markdown(f"- {item}")
    elif not compact:
        st.markdown("**🚨 Red flags / upgrade triggers:** None detected")

    if data_quality_warnings:
        st.info("Input consistency note: " + " ".join(data_quality_warnings))

    if resources:
        st.markdown("**🧪 Likely ED resources**")
        chips = "".join([f"<span class='action-chip'>{r}</span>" for r in resources])
        st.markdown(chips, unsafe_allow_html=True)

    if actions:
        with st.expander("Recommended next actions", expanded=not compact):
            for item in actions:
                st.markdown(f"- {item}")

    if rationale and not compact:
        with st.expander("Why the acuity engine chose this level", expanded=True):
            for item in rationale:
                st.markdown(f"- {item}")

    st.caption("Demo only. A licensed clinician must confirm or override the recommendation.")




def _html(value):
    """Safely display dynamic values inside Streamlit HTML snippets."""
    if value is None:
        return "-"
    return escape(str(value))


def render_latest_evaluation_result_panel():
    """Show the latest evaluation in a clearly separated output/results pane.

    This deliberately sits below the Evaluate button so the user can tell the
    difference between input fields and generated triage output. It also makes
    the queue assignment impossible to miss.
    """
    esi = st.session_state.get("last_esi")
    patient = st.session_state.get("last_patient_record") or {}
    report = st.session_state.get("last_report", "")

    override_notice = st.session_state.get("override_save_notice")
    if override_notice:
        st.success(override_notice)
        st.session_state["override_save_notice"] = None

    if not esi and not patient:
        st.markdown(
            """
            <div class="queue-note">
                <b>Output Panel:</b> evaluate a patient to generate the ESI result, assign a patient ID, and add the case to the Live Queue.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    patient_id = patient.get("patient_id") or st.session_state.get("last_patient_id") or "Not assigned"
    chief_complaint = patient.get("chief_complaint") or "Current evaluation"
    queue_status = patient.get("status") or "Added to queue"
    queue_count = len(st.session_state.get("patient_queue", []))
    esi_label = esi.get("esi_label") or patient.get("esi_label") or f"ESI-{esi.get('esi_level', '-')}"
    priority_score = esi.get("priority_score", patient.get("priority_score", "-"))
    escalation = "YES" if esi.get("escalation_required") else "No"
    fast_track = "Yes" if esi.get("fast_track_eligible") else "No"
    review = _review_text(esi.get("review_interval_minutes", "-"))

    st.markdown(
        f"""
        <div class="result-panel">
            <div class="result-kicker">Generated Output Panel — not an input section</div>
            <div class="result-title">✅ Evaluation complete: Patient {_html(patient_id)} added to the Live Queue</div>
            <div class="result-subtitle">
                This is the result from the most recent evaluation. The assigned patient ID is now visible here and in the waiting-room board.
            </div>
            <div class="result-grid">
                <div class="result-tile">
                    <div class="result-tile-label">Patient ID</div>
                    <div class="result-tile-value">{_html(patient_id)}</div>
                </div>
                <div class="result-tile">
                    <div class="result-tile-label">Chief Complaint</div>
                    <div class="result-tile-value">{_html(chief_complaint)}</div>
                </div>
                <div class="result-tile">
                    <div class="result-tile-label">Recommended Acuity</div>
                    <div class="result-tile-value">{_html(esi_label)}</div>
                </div>
                <div class="result-tile">
                    <div class="result-tile-label">Queue Status</div>
                    <div class="result-tile-value">{_html(queue_status)}</div>
                </div>
                <div class="result-tile">
                    <div class="result-tile-label">Priority Score</div>
                    <div class="result-tile-value">{_html(priority_score)}/10</div>
                </div>
                <div class="result-tile">
                    <div class="result-tile-label">Escalation</div>
                    <div class="result-tile-value">{_html(escalation)}</div>
                </div>
                <div class="result-tile">
                    <div class="result-tile-label">Fast Track</div>
                    <div class="result-tile-value">{_html(fast_track)}</div>
                </div>
                <div class="result-tile">
                    <div class="result-tile-label">Reassessment</div>
                    <div class="result-tile-value">{_html(review)}</div>
                </div>
            </div>
            <div class="result-help">
                Live Queue now contains {_html(queue_count)} patient(s). Use the Mini ED Board or the ESI Command Center tab to escalate, room, reassess, or remove this patient.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_command_agents(st.session_state.get("last_agent_outputs"), st.session_state.get("patient_queue", []), title="🤖 Agentic Command Center Output")

    st.markdown("### 🚦 Detailed ESI Result")
    render_esi_card(esi, compact=False)

    render_override_panel(
        esi,
        key_prefix=f"assessment_result_{patient_id}",
        patient_id=patient_id if patient_id != "Not assigned" else None,
    )

    if report:
        with st.expander("Assessment report", expanded=False):
            st.markdown(report)


def load_patient_queue_from_backend():
    """Load the persisted waiting-room queue from the Flask backend."""
    try:
        response = requests.get(f"{API_URL}/queue", timeout=3)
        if response.status_code == 200:
            queue = response.json()
            return queue if isinstance(queue, list) else []
    except Exception:
        pass
    return []


def sync_patient_queue_to_backend():
    """Persist the current Streamlit queue to the Flask backend."""
    try:
        requests.post(
            f"{API_URL}/queue",
            json={"queue": st.session_state.get("patient_queue", [])},
            timeout=3,
        )
    except Exception:
        # Keep the UI usable even if the backend is temporarily unavailable.
        pass


def _max_patient_counter(queue):
    """Find the highest numeric P-### id in the queue so IDs continue after refresh."""
    max_id = 0
    for patient in queue or []:
        raw_id = str(patient.get("patient_id", ""))
        try:
            if raw_id.startswith("P-"):
                max_id = max(max_id, int(raw_id.split("-", 1)[1]))
        except Exception:
            continue
    return max_id


def initialise_patient_queue(force_reload=False):
    """Create Streamlit containers and load the persisted waiting-room queue once."""
    if force_reload or "patient_queue" not in st.session_state:
        persisted_queue = load_patient_queue_from_backend()
        st.session_state["patient_queue"] = persisted_queue
        st.session_state["queue_counter"] = _max_patient_counter(persisted_queue)
    if "queue_counter" not in st.session_state:
        st.session_state["queue_counter"] = _max_patient_counter(st.session_state.get("patient_queue", []))
    if "override_audit" not in st.session_state:
        st.session_state["override_audit"] = []
    if "audit_events" not in st.session_state:
        st.session_state["audit_events"] = []
    if "queue_just_added_id" not in st.session_state:
        st.session_state["queue_just_added_id"] = None
    if "override_save_notice" not in st.session_state:
        st.session_state["override_save_notice"] = None
    if "last_agent_outputs" not in st.session_state:
        st.session_state["last_agent_outputs"] = None



DEFAULT_PATIENT_FORM_VALUES = {
    "input_age": 50,
    "input_sex_input": "Male",
    "input_sbp": 120,
    "input_chol": 200,
    "input_hr": 80,
    "input_fbs_input": "No",
    "input_cp_input": "No active chest pain / not applicable",
    "input_chief_complaint": "Other",
    "input_active_chest_pain_checkbox": False,
    "input_temperature_f": 98.6,
    "input_respiratory_rate": 16,
    "input_oxygen_saturation": 98,
    "input_pain_score": 0,
    "input_mental_status": "Alert",
    "input_arrival_mode": "Walk-in",
    "input_expected_resources": [],
    "input_immunocompromised": False,
    "input_pregnant": False,
    "input_anticoagulants": False,
    "input_suicidal_homicidal": False,
    "input_can_walk": True,
    "input_notes": "",
}


def initialise_patient_form_defaults():
    """Seed patient intake widgets so the Clear Form button can restore them."""
    for key, value in DEFAULT_PATIENT_FORM_VALUES.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "form_reset_notice" not in st.session_state:
        st.session_state["form_reset_notice"] = None


def reset_patient_form_inputs():
    """Reset only the patient intake form. This does not clear the live queue."""
    for key, value in DEFAULT_PATIENT_FORM_VALUES.items():
        st.session_state[key] = value
    st.session_state["form_reset_notice"] = "Patient intake form reset to default demo values. Live Queue was not cleared."


def clear_latest_evaluation_state():
    """Remove the last generated result panel without touching persisted audit history."""
    for key in [
        "analyst_draft",
        "reviewer_critique",
        "last_esi",
        "last_report",
        "last_probability",
        "last_priority_score",
        "last_patient_id",
        "last_patient_record",
        "last_evaluation_complete",
        "last_override",
        "last_agent_outputs",
        "queue_just_added_id",
    ]:
        if key in st.session_state:
            st.session_state[key] = None


def reset_live_demo_system():
    """Reset the live workflow back to an empty queue and blank latest result.

    This intentionally keeps the persistent audit trail as historical evidence.
    """
    cleared_count = len(st.session_state.get("patient_queue", []))
    post_audit_event(
        event_type="system_reset",
        patient_id=None,
        action="Demo system reset: live queue and latest result cleared",
        details={"cleared_patient_count": cleared_count, "audit_trail_retained": True},
    )
    st.session_state["patient_queue"] = []
    st.session_state["queue_counter"] = 0
    clear_latest_evaluation_state()
    try:
        requests.delete(f"{API_URL}/queue", timeout=3)
    except Exception:
        sync_patient_queue_to_backend()
    st.session_state["override_save_notice"] = "Demo system reset. Live Queue is now empty. Historical audit trail was retained."


def _safe_int(value, default=99):
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def post_audit_event(event_type, patient_id=None, action="", details=None, source="streamlit_ui"):
    """Write a workflow event to the persistent Flask audit log.

    The Streamlit UI also keeps a local session copy, but the Flask endpoint writes
    the event to data/audit_trail.jsonl so nurse/queue actions survive page reruns.
    """
    if "audit_events" not in st.session_state:
        st.session_state["audit_events"] = []

    payload = {
        "event_type": event_type,
        "patient_id": patient_id,
        "action": action,
        "source": source,
        "session_id": "demo_session",
        "details": details or {},
    }
    local_copy = {"timestamp": _now_iso(), **payload}
    st.session_state["audit_events"].append(local_copy)

    try:
        requests.post(f"{API_URL}/audit", json=payload, timeout=2)
    except Exception:
        # Do not break clinical workflow UI if the backend audit endpoint is unavailable.
        pass
    return local_copy


def fetch_audit_events(limit=250):
    """Read the persistent audit trail from Flask, falling back to session events."""
    try:
        response = requests.get(f"{API_URL}/audit", params={"limit": limit}, timeout=3)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return st.session_state.get("audit_events", [])[-limit:]


def render_audit_trail(compact=False):
    """Render the nurse/workflow audit trail."""
    events = fetch_audit_events(limit=100 if compact else 300)
    if not events:
        st.info("No audit events yet. Evaluate a patient, save a nurse decision, or use queue actions to populate this trail.")
        return

    rows = []
    for event in reversed(events):
        details = event.get("details") or {}
        rows.append({
            "Time": event.get("timestamp", "-"),
            "Patient": event.get("patient_id") or "-",
            "Event": event.get("event_type", "-"),
            "Action": event.get("action", "-"),
            "ESI": details.get("esi_label") or details.get("new_esi_label") or details.get("final_nurse_esi") or details.get("recommended_esi") or "-",
            "Status": details.get("status") or details.get("new_status") or "-",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if not compact:
        with st.expander("View raw audit event details", expanded=False):
            st.json(list(reversed(events[-25:])))


def _wait_minutes(patient):
    arrival = patient.get("arrival_time")
    if not arrival:
        return 0
    try:
        arrived_at = datetime.fromisoformat(arrival)
        return max(0, int((datetime.now() - arrived_at).total_seconds() // 60))
    except Exception:
        return 0


def _queue_sort_key(patient):
    # Lower ESI number is more urgent. Then prioritize red flags, priority score, and wait time.
    return (
        _safe_int(patient.get("esi_level"), 99),
        -_safe_int(patient.get("red_flag_count"), 0),
        -_safe_float(patient.get("priority_score"), 0),
        -_wait_minutes(patient),
    )


def flow_coordinator_agent(queue):
    """Generate queue-level recommendations without changing the queue."""
    queue = list(queue or [])
    if not queue:
        return {
            "name": "Flow Coordinator Agent",
            "icon": "🚑",
            "status": "Queue empty",
            "severity": "low",
            "summary": "No active patients are currently in the Live Queue.",
            "findings": ["Evaluate a patient to populate the operational board."],
            "recommendation": "No rooming recommendation yet.",
        }

    sorted_queue = sorted(queue, key=_queue_sort_key)
    top = sorted_queue[0]
    high_acuity = [p for p in queue if _safe_int(p.get("esi_level"), 99) <= 2]
    breached = [p for p in queue if "Breached" in _breach_status(p) or "Immediate" in _breach_status(p)]
    deteriorating = [p for p in queue if "Deteriorating" in _reassessment_flag(p)]
    fast_track = [p for p in queue if p.get("fast_track_eligible") or _safe_int(p.get("esi_level"), 99) >= 4]

    findings = [
        f"Next patient to review: {top.get('patient_id', '-')}, {top.get('chief_complaint', '-')}, ESI-{top.get('esi_level', '-')}.",
        f"High-acuity patients waiting: {len(high_acuity)}.",
        f"Target-wait alerts: {len(breached)}.",
        f"Deterioration flags: {len(deteriorating)}.",
    ]
    if fast_track:
        findings.append(f"Fast-track candidates: {len(fast_track)}.")

    top_level = _safe_int(top.get("esi_level"), 99)
    if top_level <= 2 or breached or deteriorating:
        severity = "high"
        status = "Action needed"
        recommendation = f"Prioritize {top.get('patient_id', '-')} for rooming/escalation; review breached or deteriorating patients next."
    elif top_level == 3:
        severity = "medium"
        status = "Monitor queue"
        recommendation = f"Keep {top.get('patient_id', '-')} in urgent queue and reassess within target window."
    else:
        severity = "low"
        status = "Stable flow"
        recommendation = "Queue currently favors fast-track/lower-acuity workflow if staffing allows."

    return {
        "name": "Flow Coordinator Agent",
        "icon": "🚑",
        "status": status,
        "severity": severity,
        "summary": f"Queue review complete: {len(queue)} active patient(s), sorted by current ESI, red flags, priority, and wait time.",
        "findings": findings,
        "recommendation": recommendation,
        "top_patient_id": top.get("patient_id"),
    }


def _agent_card_html(agent):
    name = agent.get("name", "Agent")
    icon = agent.get("icon", "🤖")
    status = agent.get("status", "Ready")
    severity = str(agent.get("severity", "info") or "info").lower()
    if severity not in {"high", "medium", "low"}:
        severity_class = ""
    else:
        severity_class = f"agent-card-{severity}"
    summary = agent.get("summary", "")
    recommendation = agent.get("recommendation", "") or agent.get("handoff_note", "")
    findings = agent.get("findings") or []
    if not findings and agent.get("sbar"):
        sbar = agent.get("sbar") or {}
        findings = [f"{k}: {v}" for k, v in sbar.items()]
    list_items = "".join(f"<li>{_html(item)}</li>" for item in findings[:5])
    if recommendation:
        list_items += f"<li><b>Recommendation:</b> {_html(recommendation)}</li>"
    return f"""<div class="agent-card {severity_class}">
  <div class="agent-kicker">Command Agent</div>
  <div class="agent-title">{_html(icon)} {_html(name)}</div>
  <div class="agent-status">{_html(status)}</div>
  <div class="agent-summary">{_html(summary)}</div>
  <ul class="agent-list">{list_items}</ul>
</div>"""


def render_command_agents(agent_outputs=None, queue=None, title="🤖 Agentic Command Center"):
    """Render the visible non-decision-making command agents."""
    agent_outputs = agent_outputs or st.session_state.get("last_agent_outputs") or {}
    queue = queue if queue is not None else st.session_state.get("patient_queue", [])

    agents = []
    if agent_outputs.get("safety_sentinel"):
        agents.append(agent_outputs.get("safety_sentinel"))
    agents.append(flow_coordinator_agent(queue))
    if agent_outputs.get("documentation"):
        agents.append(agent_outputs.get("documentation"))

    st.markdown(f"### {title}")
    st.caption("These agents explain, coordinate, and document. They do not override the deterministic ESI safety engine or the nurse-final decision.")
    cards = "".join(_agent_card_html(agent) for agent in agents)
    st.markdown(f"<div class='agent-grid'>{cards}</div>", unsafe_allow_html=True)

def _first_item(values, fallback="Clinician review"):
    if isinstance(values, list) and values:
        return values[0]
    return fallback


def _esi_label_for_level(level):
    """Return a readable label for a final nurse-assigned ESI level."""
    labels = {
        1: "ESI-1 — Critical / Immediate Life-Saving Intervention",
        2: "ESI-2 — Emergent / High Risk",
        3: "ESI-3 — Urgent / Multiple Resources",
        4: "ESI-4 — Less Urgent / One Resource",
        5: "ESI-5 — Non-Urgent / No Resources",
    }
    return labels.get(_safe_int(level), f"ESI-{level}")




def _is_high_risk_downgrade(ai_level, nurse_level):
    """True when AI says ESI-1/2 but nurse final is ESI-4/5."""
    ai_level = _safe_int(ai_level, None)
    nurse_level = _safe_int(nurse_level, None)
    return ai_level in [1, 2] and nurse_level in [4, 5]


def _patient_event_summary(event):
    """Compress an audit event into one readable patient-timeline row."""
    details = event.get("details") or {}
    event_type = event.get("event_type", "-")
    esi_bits = []
    if details.get("old_esi_level") and details.get("new_esi_level"):
        esi_bits.append(f"ESI-{details.get('old_esi_level')} → ESI-{details.get('new_esi_level')}")
    elif details.get("recommended_esi") and details.get("final_nurse_esi"):
        esi_bits.append(f"AI {details.get('recommended_esi')} → Nurse {details.get('final_nurse_esi')}")
    elif details.get("esi_label"):
        esi_bits.append(str(details.get("esi_label")))
    elif details.get("new_esi_label"):
        esi_bits.append(str(details.get("new_esi_label")))

    notes = []
    if details.get("classification"):
        notes.append(str(details.get("classification")))
    if details.get("high_risk_downgrade"):
        notes.append("High-risk downgrade documented")
    if details.get("status") or details.get("new_status"):
        notes.append(str(details.get("status") or details.get("new_status")))
    if details.get("note"):
        notes.append(str(details.get("note"))[:100])
    if details.get("reason"):
        notes.append(str(details.get("reason"))[:100])

    return {
        "Time": event.get("timestamp", "-"),
        "Event": event_type,
        "Action": event.get("action", "-"),
        "ESI / Change": "; ".join(esi_bits) if esi_bits else "-",
        "Notes": " | ".join(notes) if notes else "-",
    }


def render_patient_timeline(patient):
    """Show a patient-specific timeline inside the patient detail modal."""
    patient_id = patient.get("patient_id")
    if not patient_id:
        return

    st.markdown("---")
    st.markdown("### 🕒 Patient Timeline")

    events = [e for e in fetch_audit_events(limit=500) if e.get("patient_id") == patient_id]
    rows = [_patient_event_summary(e) for e in events]

    if not rows:
        st.info("No audit timeline entries found yet for this patient.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    reassessments = patient.get("reassessments") or []
    if reassessments:
        with st.expander("Reassessment history details", expanded=False):
            st.json(reassessments)

def apply_nurse_override_to_queue(patient_id, override_record):
    """Apply the final nurse ESI to the live queue, not just the audit log.

    The deterministic ESI recommendation is preserved as ai_esi_* fields.
    The board-visible ESI is updated to the nurse-final level so the queue
    reflects the clinician's decision immediately after Save Override.
    """
    if not patient_id:
        return None

    initialise_patient_queue()
    final_esi = override_record.get("final_nurse_esi", "")
    final_level = _safe_int(str(final_esi).replace("ESI-", ""), None)
    if final_level is None:
        return None

    decision = override_record.get("decision", "Accept AI recommendation")
    for patient in st.session_state.get("patient_queue", []):
        if patient.get("patient_id") != patient_id:
            continue

        if "ai_esi_level" not in patient:
            patient["ai_esi_level"] = patient.get("esi_level")
            patient["ai_esi_label"] = patient.get("esi_label")
            patient["ai_priority_score"] = patient.get("priority_score")

        patient["override"] = override_record
        patient["final_nurse_esi"] = final_esi
        patient["final_nurse_esi_level"] = final_level
        patient["nurse_decision"] = decision
        patient["nurse_override_reason"] = override_record.get("reason", "")
        patient["esi_level"] = final_level
        patient["esi_label"] = _esi_label_for_level(final_level)
        patient["last_status_update"] = _now_iso()

        high_risk_downgrade = _is_high_risk_downgrade(patient.get("ai_esi_level"), final_level)
        patient["high_risk_downgrade"] = bool(high_risk_downgrade)
        patient["safety_flag"] = _override_timing_flag(patient)

        if decision == "Accept AI recommendation":
            patient["status"] = f"Waiting — nurse confirmed {final_esi}"
            patient["next_action"] = patient.get("next_action") or "Continue recommended workflow"
        elif final_level in [1, 2]:
            patient["status"] = f"Waiting — nurse override to {final_esi} / escalate"
            patient["next_action"] = "Nurse override: urgent clinician review"
        elif high_risk_downgrade:
            patient["status"] = f"Waiting — nurse downgrade to {final_esi} / high-risk downgrade documented"
            patient["next_action"] = "High-risk downgrade documented; monitor and reassess per clinician judgment"
        else:
            patient["status"] = f"Waiting — nurse override to {final_esi}"
            patient["next_action"] = "Nurse override recorded; manage per final acuity"

        if st.session_state.get("last_patient_id") == patient_id:
            st.session_state["last_patient_record"] = patient

        sync_patient_queue_to_backend()
        return patient

    return None


def add_patient_to_queue(final_data, vitals, notes=""):
    """Add the just-evaluated patient to a real live-session waiting-room queue."""
    initialise_patient_queue()
    esi = final_data.get("esi") or {}
    st.session_state["queue_counter"] += 1
    patient_id = f"P-{st.session_state['queue_counter']:03d}"

    red_flags = esi.get("red_flags") or []
    resources = esi.get("likely_resources") or []
    actions = esi.get("recommended_next_actions") or []
    esi_level = _safe_int(esi.get("esi_level"), 99)

    if esi.get("escalation_required") or esi_level in [1, 2]:
        status = "Waiting — Escalate"
    elif esi.get("fast_track_eligible"):
        status = "Waiting — Fast Track"
    else:
        status = "Waiting"

    patient = {
        "patient_id": patient_id,
        "arrival_time": _now_iso(),
        "chief_complaint": vitals.get("chief_complaint", "Current evaluation"),
        "age": vitals.get("age"),
        "sex": "Male" if vitals.get("sex") == 1 else "Female",
        "esi_level": esi_level,
        "esi_label": esi.get("esi_label", f"ESI-{esi_level}"),
        "priority_score": esi.get("priority_score", final_data.get("priority_score", 0)),
        "ai_esi_level": esi_level,
        "ai_esi_label": esi.get("esi_label", f"ESI-{esi_level}"),
        "ai_priority_score": esi.get("priority_score", final_data.get("priority_score", 0)),
        "final_nurse_esi": "-",
        "final_nurse_esi_level": None,
        "nurse_decision": None,
        "nurse_override_reason": "",
        "red_flags": red_flags,
        "red_flag_count": len(red_flags),
        "fast_track_eligible": bool(esi.get("fast_track_eligible")),
        "recommended_resources": resources,
        "reassessment_interval": esi.get("review_interval_minutes", "-"),
        "next_action": _first_item(actions),
        "status": status,
        "vitals": vitals,
        "notes": notes,
        "disease_probability": final_data.get("disease_probability"),
        "report": final_data.get("report", ""),
        "esi_result": esi,
        "agent_outputs": final_data.get("agent_outputs", {}),
        "override": None,
    }
    st.session_state["patient_queue"].append(patient)
    st.session_state["last_patient_record"] = patient
    st.session_state["last_patient_id"] = patient_id
    st.session_state["queue_just_added_id"] = patient_id
    sync_patient_queue_to_backend()

    post_audit_event(
        event_type="patient_added_to_queue",
        patient_id=patient_id,
        action="Patient evaluated and added to Live Session Queue",
        details={
            "chief_complaint": patient.get("chief_complaint"),
            "esi_level": patient.get("esi_level"),
            "esi_label": patient.get("esi_label"),
            "priority_score": patient.get("priority_score"),
            "red_flag_count": patient.get("red_flag_count"),
            "red_flags": patient.get("red_flags"),
            "fast_track_eligible": patient.get("fast_track_eligible"),
            "recommended_resources": patient.get("recommended_resources"),
            "status": patient.get("status"),
            "next_action": patient.get("next_action"),
            "agent_outputs": {
                "safety_sentinel": (patient.get("agent_outputs") or {}).get("safety_sentinel", {}).get("summary"),
                "documentation": (patient.get("agent_outputs") or {}).get("documentation", {}).get("audit_summary"),
            },
        },
    )
    return patient


def update_patient_status(patient_id, status, action_label="Queue status updated"):
    initialise_patient_queue()
    for patient in st.session_state["patient_queue"]:
        if patient.get("patient_id") == patient_id:
            old_status = patient.get("status")
            patient["status"] = status
            patient["last_status_update"] = _now_iso()
            post_audit_event(
                event_type="queue_status_update",
                patient_id=patient_id,
                action=action_label,
                details={
                    "chief_complaint": patient.get("chief_complaint"),
                    "esi_label": patient.get("esi_label"),
                    "old_status": old_status,
                    "new_status": status,
                    "priority_score": patient.get("priority_score"),
                    "red_flags": patient.get("red_flags"),
                },
            )
            import copy
            st.session_state["patient_queue"] = copy.deepcopy(st.session_state["patient_queue"])
            sync_patient_queue_to_backend()
            return patient
    return None


def _mental_status_rank(status):
    """Higher rank means worse mental status for deterioration comparisons."""
    text = str(status or "Alert").strip().lower()
    mapping = {
        "alert": 0,
        "confused/altered": 1,
        "confused": 1,
        "altered": 1,
        "voice/pain only": 2,
        "voice only": 2,
        "pain only": 2,
        "unresponsive": 3,
    }
    return mapping.get(text, 0)


def _compact_change(label, old_value, new_value, unit=""):
    if old_value is None or new_value is None:
        return None
    return f"{label}: {old_value}{unit} → {new_value}{unit}"


def detect_deterioration(old_vitals, new_vitals, old_esi_level, new_esi_level):
    """Compare old and new vitals and return deterioration triggers.

    This is a deterministic demo safety layer. It is intentionally conservative:
    worsening oxygen, heart rate, blood pressure, respiratory rate, pain, mental
    status, or an upgraded ESI acuity creates a deterioration flag.
    """
    triggers = []
    improvements = []

    old_spo2 = _safe_int(old_vitals.get("oxygen_saturation"), None)
    new_spo2 = _safe_int(new_vitals.get("oxygen_saturation"), None)
    if new_spo2 is not None and new_spo2 < 90:
        triggers.append(f"Severe hypoxia on reassessment: SpO₂ {new_spo2}%")
    elif new_spo2 is not None and new_spo2 < 92:
        triggers.append(f"Low oxygen saturation on reassessment: SpO₂ {new_spo2}%")
    if old_spo2 is not None and new_spo2 is not None and old_spo2 - new_spo2 >= 4:
        triggers.append(_compact_change("SpO₂ dropped", old_spo2, new_spo2, "%"))
    if old_spo2 is not None and new_spo2 is not None and new_spo2 - old_spo2 >= 4:
        improvements.append(_compact_change("SpO₂ improved", old_spo2, new_spo2, "%"))

    old_hr = _safe_int(old_vitals.get("thalach"), None)
    new_hr = _safe_int(new_vitals.get("thalach"), None)
    if new_hr is not None and new_hr >= 130:
        triggers.append(f"Marked tachycardia on reassessment: HR {new_hr}/min")
    if old_hr is not None and new_hr is not None and new_hr - old_hr >= 20:
        triggers.append(_compact_change("Heart rate increased", old_hr, new_hr, "/min"))
    if old_hr is not None and new_hr is not None and old_hr - new_hr >= 20:
        improvements.append(_compact_change("Heart rate improved", old_hr, new_hr, "/min"))

    old_sbp = _safe_int(old_vitals.get("trestbps"), None)
    new_sbp = _safe_int(new_vitals.get("trestbps"), None)
    if new_sbp is not None and new_sbp < 90:
        triggers.append(f"Hypotension on reassessment: SBP {new_sbp} mm Hg")
    if new_sbp is not None and new_sbp >= 180:
        triggers.append(f"Severe hypertension on reassessment: SBP {new_sbp} mm Hg")
    if old_sbp is not None and new_sbp is not None and old_sbp - new_sbp >= 20:
        triggers.append(_compact_change("Systolic BP dropped", old_sbp, new_sbp, " mm Hg"))

    old_rr = _safe_int(old_vitals.get("respiratory_rate"), None)
    new_rr = _safe_int(new_vitals.get("respiratory_rate"), None)
    if new_rr is not None and (new_rr <= 8 or new_rr >= 30):
        triggers.append(f"Abnormal respiratory rate on reassessment: RR {new_rr}/min")
    if old_rr is not None and new_rr is not None and new_rr - old_rr >= 8:
        triggers.append(_compact_change("Respiratory rate increased", old_rr, new_rr, "/min"))

    old_pain = _safe_int(old_vitals.get("pain_score"), None)
    new_pain = _safe_int(new_vitals.get("pain_score"), None)
    if new_pain is not None and new_pain >= 8:
        triggers.append(f"Severe pain on reassessment: {new_pain}/10")
    if old_pain is not None and new_pain is not None and new_pain - old_pain >= 2:
        triggers.append(_compact_change("Pain score increased", old_pain, new_pain, "/10"))
    if old_pain is not None and new_pain is not None and old_pain - new_pain >= 2:
        improvements.append(_compact_change("Pain score improved", old_pain, new_pain, "/10"))

    old_temp = _safe_float(old_vitals.get("temperature_f"), None)
    new_temp = _safe_float(new_vitals.get("temperature_f"), None)
    if new_temp is not None and (new_temp >= 100.4 or new_temp <= 95.0):
        triggers.append(f"Abnormal temperature on reassessment: {new_temp:.1f}°F")

    old_mental = str(old_vitals.get("mental_status", "Alert"))
    new_mental = str(new_vitals.get("mental_status", "Alert"))
    if _mental_status_rank(new_mental) > _mental_status_rank(old_mental):
        triggers.append(f"Mental status worsened: {old_mental} → {new_mental}")
    elif _mental_status_rank(new_mental) < _mental_status_rank(old_mental):
        improvements.append(f"Mental status improved: {old_mental} → {new_mental}")

    old_level = _safe_int(old_esi_level, None)
    new_level = _safe_int(new_esi_level, None)
    if old_level is not None and new_level is not None:
        if new_level < old_level:
            triggers.append(f"ESI upgraded after reassessment: ESI-{old_level} → ESI-{new_level}")
        elif new_level > old_level:
            improvements.append(f"ESI downgraded after reassessment: ESI-{old_level} → ESI-{new_level}")

    # De-duplicate while preserving order.
    def dedupe(items):
        seen = set()
        out = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out

    return dedupe(triggers), dedupe(improvements)


def run_patient_reassessment(patient_id, new_vitals, reassessment_note=""):
    """Run the reassessment/deterioration workflow and update the live queue."""
    initialise_patient_queue()
    if assess_esi_acuity is None:
        st.error("Could not load the ESI acuity engine for reassessment.")
        return None

    for patient in st.session_state.get("patient_queue", []):
        if patient.get("patient_id") != patient_id:
            continue

        old_vitals = dict(patient.get("vitals") or {})
        updated_vitals = dict(old_vitals)
        updated_vitals.update(new_vitals or {})

        old_level = _safe_int(patient.get("esi_level"), 99)

        disease_probability = _safe_float(patient.get("disease_probability"), 0.0)
        combined_note = "\n".join([str(patient.get("notes") or ""), str(reassessment_note or "")]).strip()
        new_esi = assess_esi_acuity(updated_vitals, notes=combined_note, disease_probability=disease_probability)
        new_level = _safe_int(new_esi.get("esi_level"), old_level)
        triggers, improvements = detect_deterioration(old_vitals, updated_vitals, old_level, new_level)

        if triggers or new_level < old_level:
            classification = "Deteriorated"
            status = f"Deteriorating — reassessed to ESI-{new_level}"
            if new_level <= 2:
                status += " / escalate"
            next_action = "Reassessment shows deterioration: escalate and re-triage"
        elif new_level > old_level:
            classification = "Improved / lower acuity"
            status = f"Reassessed — improved/lower acuity to ESI-{new_level}"
            next_action = "Continue queue management per reassessed acuity"
        else:
            classification = "Stable"
            status = f"Reassessed — stable at ESI-{new_level}"
            next_action = patient.get("next_action") or _first_item(new_esi.get("recommended_next_actions"))

        reassessment_record = {
            "timestamp": _now_iso(),
            "old_vitals": old_vitals,
            "new_vitals": updated_vitals,
            "old_esi_level": old_level,
            "old_esi_label": patient.get("esi_label"),
            "new_esi_level": new_level,
            "new_esi_label": new_esi.get("esi_label"),
            "classification": classification,
            "deterioration_triggers": triggers,
            "improvements": improvements,
            "note": reassessment_note,
        }

        patient.setdefault("original_vitals", old_vitals)
        patient.setdefault("reassessments", []).append(reassessment_record)
        patient["last_reassessment"] = reassessment_record
        patient["deterioration_status"] = classification
        patient["deterioration_triggers"] = triggers
        patient["improvement_notes"] = improvements
        patient["vitals"] = updated_vitals
        patient["esi_result"] = new_esi
        patient["esi_level"] = new_level
        patient["esi_label"] = new_esi.get("esi_label", _esi_label_for_level(new_level))
        patient["priority_score"] = new_esi.get("priority_score", patient.get("priority_score"))
        patient["red_flags"] = new_esi.get("red_flags", [])
        patient["red_flag_count"] = len(new_esi.get("red_flags", []))
        patient["fast_track_eligible"] = bool(new_esi.get("fast_track_eligible"))
        patient["recommended_resources"] = new_esi.get("likely_resources", patient.get("recommended_resources", []))
        patient["reassessment_interval"] = new_esi.get("review_interval_minutes", patient.get("reassessment_interval"))
        patient["next_action"] = next_action
        patient["status"] = status
        patient["last_status_update"] = _now_iso()

        if st.session_state.get("last_patient_id") == patient_id:
            st.session_state["last_patient_record"] = patient
            st.session_state["last_esi"] = new_esi

        import copy
        # Force Streamlit to recognize the nested dictionary mutation.
        # Runtime debug file writes were removed so reassessment works on Windows,
        # Linux, Railway, and GitHub without a machine-specific path.
        st.session_state["patient_queue"] = copy.deepcopy(st.session_state.get("patient_queue", []))
        sync_patient_queue_to_backend()

        post_audit_event(
            event_type="patient_reassessment",
            patient_id=patient_id,
            action=f"Patient reassessed: {classification}",
            details={
                "chief_complaint": patient.get("chief_complaint"),
                "old_esi_level": old_level,
                "new_esi_level": new_level,
                "new_esi_label": patient.get("esi_label"),
                "classification": classification,
                "deterioration_triggers": triggers,
                "improvements": improvements,
                "status": status,
                "next_action": next_action,
                "old_vitals": old_vitals,
                "new_vitals": updated_vitals,
                "note": reassessment_note,
            },
        )
        st.session_state["override_save_notice"] = f"Reassessment saved for {patient_id}: {classification}. Queue updated to ESI-{new_level}."
        return patient

    st.error("Patient not found in queue for reassessment.")
    return None


def remove_patient_from_queue(patient_id):
    initialise_patient_queue()
    patient = next((p for p in st.session_state["patient_queue"] if p.get("patient_id") == patient_id), None)
    if patient:
        post_audit_event(
            event_type="patient_removed_from_queue",
            patient_id=patient_id,
            action="Patient discharged/removed from Live Session Queue",
            details={
                "chief_complaint": patient.get("chief_complaint"),
                "esi_label": patient.get("esi_label"),
                "status": patient.get("status"),
                "wait_minutes": _wait_minutes(patient),
            },
        )
    st.session_state["patient_queue"] = [
        patient for patient in st.session_state["patient_queue"]
        if patient.get("patient_id") != patient_id
    ]
    sync_patient_queue_to_backend()



def _target_wait_minutes(patient):
    """Return the target wait/reassessment window for queue timing alerts."""
    review = patient.get("reassessment_interval")
    if isinstance(review, str):
        if review.strip().lower() in ["immediate", "now", "stat"]:
            return 0
        try:
            return int(float(review.replace("min", "").strip()))
        except Exception:
            pass
    try:
        return int(review)
    except Exception:
        pass

    esi_level = _safe_int(patient.get("esi_level"), 99)
    return {1: 0, 2: 0, 3: 30, 4: 60, 5: 120}.get(esi_level, 60)


def _target_wait_text(patient):
    target = _target_wait_minutes(patient)
    return "Immediate" if target == 0 else f"{target} min"


def _breach_status(patient):
    """Readable timing status for the waiting-room board."""
    status_text = str(patient.get("status", "")).lower()
    if "roomed" in status_text:
        return "Roomed"
    if "discharg" in status_text:
        return "Removed"

    wait = _wait_minutes(patient)
    target = _target_wait_minutes(patient)
    if target == 0:
        return "BREACHED — room now" if wait >= 1 else "Needs room now"
    if wait >= target:
        return "BREACHED"
    if wait >= max(1, int(target * 0.8)):
        return "Approaching"
    return "OK"


def _override_timing_flag(patient):
    """Flag potentially risky downgrades while preserving nurse authority."""
    ai_level = _safe_int(patient.get("ai_esi_level"), None)
    nurse_level = _safe_int(patient.get("final_nurse_esi_level"), None)
    if ai_level in [1, 2] and nurse_level in [4, 5]:
        return "High-risk downgrade"
    if ai_level and nurse_level and nurse_level < ai_level:
        return "Upgraded by nurse"
    if ai_level and nurse_level and nurse_level > ai_level:
        return "Downgraded by nurse"
    return "-"


def _reassessment_flag(patient):
    last = patient.get("last_reassessment") or {}
    classification = patient.get("deterioration_status") or last.get("classification")
    if not classification:
        status = str(patient.get("status", "")).lower()
        if "reassess" in status:
            return "Needs reassess"
        return "-"
    if str(classification).lower().startswith("deteriorated"):
        return "Deteriorated"
    if str(classification).lower().startswith("stable"):
        return "Stable"
    if "improved" in str(classification).lower():
        return "Improved"
    return str(classification)


def _queue_dataframe(queue, compact=False):
    rows = []
    for patient in queue:
        row = {
            "Patient": patient.get("patient_id"),
            "Current Queue ESI": f"ESI-{patient.get('esi_level', '-')}",
            "AI Recommended ESI": patient.get("ai_esi_label", patient.get("esi_label", "-")),
            "Nurse Final ESI": patient.get("final_nurse_esi", "-"),
            "Wait": f"{_wait_minutes(patient)} min",
            "Target Wait": _target_wait_text(patient),
            "Breach / Timing": _breach_status(patient),
            "Safety Flag": _override_timing_flag(patient),
            "Reassess / Deterioration": _reassessment_flag(patient),
            "Complaint": patient.get("chief_complaint", "-"),
            "Status": patient.get("status", "Waiting"),
        }
        if not compact:
            row.update({
                "AI Priority Score": patient.get("priority_score", "-"),
                "Override Flag": _override_timing_flag(patient),
                "Last Reassessment": _reassessment_flag(patient),
                "Red Flags": patient.get("red_flag_count", 0),
                "Fast Track": "Yes" if patient.get("fast_track_eligible") else "No",
                "Next Action": patient.get("next_action", "Clinician review"),
            })
        rows.append(row)
    return pd.DataFrame(rows)


@st.dialog("Patient Details & Actions", width="large")
def patient_detail_modal(patient_id, safe_prefix):
    queue = st.session_state.get("patient_queue", [])
    selected_patient = next((p for p in queue if p.get("patient_id") == patient_id), None)
    if not selected_patient:
        st.error("Patient not found in queue.")
        return

    st.subheader(f"Patient ID: {patient_id}")

    # Action Buttons
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("🚨 Escalate", key=f"{safe_prefix}_{patient_id}_escalate", use_container_width=True):
            update_patient_status(patient_id, "Escalated — provider review now", action_label="Nurse escalated patient from queue")
            st.rerun()
    with b2:
        if st.button("🛏️ Room Patient", key=f"{safe_prefix}_{patient_id}_room", use_container_width=True):
            update_patient_status(patient_id, "Roomed / in treatment area", action_label="Nurse roomed patient")
            st.rerun()
    with b3:
        if st.button("🔁 Mark Reassess", key=f"{safe_prefix}_{patient_id}_reassess", use_container_width=True):
            update_patient_status(patient_id, "Needs reassessment", action_label="Nurse marked patient for reassessment")
            st.rerun()
    with b4:
        if st.button("✅ Discharge / Remove", key=f"{safe_prefix}_{patient_id}_remove", use_container_width=True):
            remove_patient_from_queue(patient_id)
            st.rerun()

    st.markdown("---")
    
    # Detailed Information
    d1, d2 = st.columns([1, 1])
    with d1:
        st.markdown(f"**Chief complaint:** {selected_patient.get('chief_complaint')}")
        st.markdown(f"**Arrived:** {selected_patient.get('arrival_time')}")
        st.markdown(f"**Wait:** {_wait_minutes(selected_patient)} min")
        st.markdown(f"**Target wait:** {_target_wait_text(selected_patient)}")
        st.markdown(f"**Breach / timing:** {_breach_status(selected_patient)}")
        st.markdown(f"**Status:** {selected_patient.get('status')}")
        
        st.markdown("---")
        st.markdown("### Clinical Overrides & Acuity")
        if selected_patient.get("final_nurse_esi"):
            st.markdown(f"**Final nurse ESI:** {selected_patient.get('final_nurse_esi')}")
            st.markdown(f"**Original AI ESI:** {selected_patient.get('ai_esi_label', selected_patient.get('esi_label'))}")
            flag = _override_timing_flag(selected_patient)
            if flag != "-":
                st.warning(f"Override flag: {flag}")
        else:
            st.markdown(f"**AI Recommended ESI:** {selected_patient.get('ai_esi_label', selected_patient.get('esi_label'))}")
            
        st.markdown("---")
        st.markdown(f"**Next action:** {selected_patient.get('next_action')}")
        resources = selected_patient.get("recommended_resources") or []
        if resources:
            st.markdown("**Likely resources:** " + ", ".join(resources))
    with d2:
        render_esi_card(selected_patient.get("esi_result"), compact=True)

    last_reassessment = selected_patient.get("last_reassessment") or {}
    if last_reassessment:
        st.markdown("---")
        classification = last_reassessment.get("classification", "Reassessed")
        triggers = last_reassessment.get("deterioration_triggers") or []
        improvements = last_reassessment.get("improvements") or []
        if str(classification).lower().startswith("deteriorated"):
            st.markdown(
                f"<div class='deterioration-banner'>Latest reassessment: {classification}. Current queue acuity is ESI-{selected_patient.get('esi_level')}.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div class='stable-banner'>Latest reassessment: {classification}. Current queue acuity is ESI-{selected_patient.get('esi_level')}.</div>",
                unsafe_allow_html=True,
            )
        if triggers:
            st.markdown("**Deterioration triggers:**")
            for trigger in triggers:
                st.markdown(f"- {trigger}")
        if improvements:
            st.markdown("**Improvement notes:**")
            for item in improvements:
                st.markdown(f"- {item}")

    render_patient_timeline(selected_patient)

    st.markdown("---")
    with st.expander("🔁 Reassess vitals / deterioration engine", expanded="reassess" in str(selected_patient.get("status", "")).lower()):
        st.markdown(
            "Enter repeat vitals from the waiting room. The app compares old vs new values, recalculates ESI, updates the Live Queue, and writes an audit event."
        )
        current_vitals = selected_patient.get("vitals") or {}


        with st.form(key=f"{safe_prefix}_{patient_id}_reassess_form"):
            r1, r2, r3 = st.columns(3)
            with r1:
                reassess_hr = st.number_input("New heart rate / min", min_value=30, max_value=260, value=_safe_int(current_vitals.get("thalach"), 80), key=f"{safe_prefix}_{patient_id}_re_hr_val")
                reassess_sbp = st.number_input("New systolic BP", min_value=50, max_value=260, value=_safe_int(current_vitals.get("trestbps"), 120), key=f"{safe_prefix}_{patient_id}_re_sbp_val")
            with r2:
                reassess_spo2 = st.number_input("New oxygen saturation SpO₂ (%)", min_value=50, max_value=100, value=_safe_int(current_vitals.get("oxygen_saturation"), 98), key=f"{safe_prefix}_{patient_id}_re_spo2_val")
                reassess_rr = st.number_input("New respiratory rate / min", min_value=4, max_value=60, value=_safe_int(current_vitals.get("respiratory_rate"), 16), key=f"{safe_prefix}_{patient_id}_re_rr_val")
            with r3:
                reassess_temp = st.number_input("New temperature (°F)", min_value=90.0, max_value=110.0, step=0.1, value=float(current_vitals.get("temperature_f", 98.6) or 98.6), key=f"{safe_prefix}_{patient_id}_re_temp_val")
                reassess_pain = st.number_input("New pain score (0-10)", min_value=0, max_value=10, value=_safe_int(current_vitals.get("pain_score"), 0), key=f"{safe_prefix}_{patient_id}_re_pain_val")

            mental_options = ["Alert", "Confused/Altered", "Voice/Pain Only", "Unresponsive"]
            current_mental = str(current_vitals.get("mental_status", "Alert"))
            mental_index = mental_options.index(current_mental) if current_mental in mental_options else 0
            
            reassess_mental = st.selectbox("New mental status", mental_options, index=mental_index, key=f"{safe_prefix}_{patient_id}_re_mental_val")
            reassess_active_chest_pain = st.checkbox("Active chest pain/cardiac symptoms now present", value=bool(current_vitals.get("active_chest_pain", False)), key=f"{safe_prefix}_{patient_id}_re_cp_val")
            reassessment_note = st.text_area("Reassessment note", placeholder="Example: patient reports worsening shortness of breath; SpO₂ dropped; now confused; pain increased...", key=f"{safe_prefix}_{patient_id}_re_note_val")

            submit_reassessment = st.form_submit_button(
                "Run Reassessment and Update Queue",
                use_container_width=True,
                type="primary"
            )

        if submit_reassessment:
            new_vitals = {
                "thalach": reassess_hr,
                "trestbps": reassess_sbp,
                "oxygen_saturation": reassess_spo2,
                "respiratory_rate": reassess_rr,
                "temperature_f": reassess_temp,
                "pain_score": reassess_pain,
                "mental_status": reassess_mental,
                "active_chest_pain": reassess_active_chest_pain,
            }
            

            run_patient_reassessment(patient_id, new_vitals, reassessment_note)
            st.success("✅ Reassessment complete! Please close this popup window to see the updated Live Queue.")

def render_command_board(latest_esi=None, key_prefix="queue", show_actions=True):
    """Render the real live-session waiting-room queue.

    The old version displayed computer-generated placeholder rows. This version
    only shows patients submitted through the evaluation form during the current
    Streamlit session.
    """
    

    initialise_patient_queue()
    queue = st.session_state.get("patient_queue", [])
    safe_prefix = str(key_prefix).replace(" ", "_").replace("-", "_")

    if not queue:
        st.markdown(
            """
            <div class="queue-note">
                <b>Live Queue:</b> no submitted patients yet. Run a patient evaluation and the patient will be added here automatically. No computer-generated waiting-room rows are being shown.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    sorted_queue = sorted(queue, key=_queue_sort_key)
    immediate_count = sum(1 for p in queue if _safe_int(p.get("esi_level"), 99) in [1, 2] or p.get("red_flag_count", 0) > 0)
    deteriorating_count = sum(1 for p in queue if str(_reassessment_flag(p)).lower().startswith("deteriorated"))
    fast_track_count = sum(1 for p in queue if p.get("fast_track_eligible"))

    st.markdown(
        """
        <div class="queue-note">
            <b>Live Queue:</b> built from real submitted patients and persisted through the Flask backend. Lower ESI numbers are more critical. The board is sorted by current queue ESI, red flags, AI priority score, and wait time. Reassessed patients are updated in-place.
        </div>
        <div class="timing-help">
            <b>Timing guide:</b> Wait is elapsed time in the queue. Target Wait is the expected review/rooming window. Breach / Timing tells you whether the patient is OK, approaching target, or overdue.
            <br><i>Click any patient row to open the detailed view and clinical actions.</i>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Patients in Queue", len(queue))
    m2.metric("Escalation / Red-Flag", immediate_count)
    m3.metric("Deteriorating", deteriorating_count)
    m4.metric("Fast-Track Candidates", fast_track_count)

    # Render Compact Dataframe with Selection
    df = _queue_dataframe(sorted_queue, compact=True)
    
    st.caption("ℹ️ *To reopen a patient you just closed, click their row once to deselect it, then click it again.*")
    event = st.dataframe(
        df, 
        use_container_width=True, 
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{safe_prefix}_dataframe"
    )

    # Trigger Dialog on Selection (Only if newly selected to prevent rerun loops)
    state_key = f"{safe_prefix}_last_selection"
    current_selection = event.selection.rows[0] if event.selection and event.selection.rows else None

    if current_selection is not None:
        if st.session_state.get(state_key) != current_selection:
            st.session_state[state_key] = current_selection
            patient_id = df.iloc[current_selection]["Patient"]
            patient_detail_modal(patient_id, safe_prefix)
    else:
        st.session_state[state_key] = None

    # Queue Action Buttons
    c1, c2, c3 = st.columns([1.5, 1.5, 7])
    with c1:
        if st.button("🔄 Refresh live queue", key=f"{safe_prefix}_refresh_queue"):
            st.rerun()
    with c2:
        if st.button("🧹 Clear entire live queue", key=f"{safe_prefix}_clear_queue"):
            post_audit_event(
                event_type="queue_cleared",
                patient_id=None,
                action="Entire Live Session Queue cleared",
                details={"cleared_patient_count": len(st.session_state.get("patient_queue", []))},
            )
            st.session_state["patient_queue"] = []
            st.session_state["queue_counter"] = 0
            sync_patient_queue_to_backend()
            st.rerun()


def render_override_panel(esi, key_prefix="latest", patient_id=None):
    """Render and persist the nurse confirmation/override panel.

    Streamlit renders all tabs during a run, so this panel may appear in more
    than one location on the page. Each widget therefore needs a unique key.
    Saving the panel now writes a persistent audit event through the Flask API.
    """
    if not esi:
        return

    resolved_patient_id = patient_id or st.session_state.get("last_patient_id")
    if not resolved_patient_id or resolved_patient_id == "Not assigned":
        st.info("Run an evaluation to assign a patient ID before saving an override.")
        return

    safe_prefix = str(key_prefix).replace(" ", "_").replace("-", "_")
    recommended_level = _safe_int(esi.get("esi_level"), 3)
    recommended_index = max(0, min(4, recommended_level - 1))
    esi_options = ["ESI-1", "ESI-2", "ESI-3", "ESI-4", "ESI-5"]

    st.markdown('<div class="override-box">', unsafe_allow_html=True)
    st.markdown("### 👩‍⚕️ Nurse Confirmation / Override")
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        decision = st.radio(
            "Clinician action",
            ["Accept AI recommendation", "Upgrade urgency / make patient more critical", "Downgrade urgency / make patient less critical"],
            help="With ESI, lower numbers are more urgent. Upgrade = move toward ESI-1. Downgrade = move toward ESI-5.",
            horizontal=False,
            key=f"{safe_prefix}_override_decision",
        )
    with c2:
        final_esi = st.selectbox(
            "Final nurse ESI",
            esi_options,
            index=recommended_index,
            key=f"{safe_prefix}_final_nurse_esi",
        )
        st.caption(f"AI recommended: {esi.get('esi_label', f'ESI-{recommended_level}')}")
    with c3:
        reason = st.text_area(
            "Reason / clinical judgement note",
            placeholder="Example: patient appears worse than vitals suggest, unstable gait, concerning story, or clinician downgrades after exam...",
            key=f"{safe_prefix}_override_reason",
        )

    final_level = _safe_int(str(final_esi).replace("ESI-", ""), recommended_level)
    high_risk_downgrade = _is_high_risk_downgrade(recommended_level, final_level)
    accept_mismatch = decision == "Accept AI recommendation" and final_level != recommended_level

    if high_risk_downgrade:
        st.markdown(
            "<div class='safety-warning'>⚠️ High-risk downgrade detected: AI recommended ESI-1/ESI-2, but the nurse final ESI is ESI-4/ESI-5. A clinical reason is required before saving.</div>",
            unsafe_allow_html=True,
        )
    if accept_mismatch:
        st.warning("Accept AI recommendation should keep the final nurse ESI the same as the AI recommendation. Choose upgrade/downgrade if you want to change acuity.")

    save_clicked = st.button(
        "Save Override / Confirmation",
        use_container_width=True,
        key=f"{safe_prefix}_save_override",
    )

    if save_clicked:
        st.warning("Save clicked block entered!")
        if accept_mismatch:
            st.error("Save blocked: either keep the final nurse ESI equal to the AI recommendation, or choose upgrade/downgrade.")
        elif high_risk_downgrade and not str(reason or "").strip():
            st.error("Save blocked: high-risk downgrade requires a documented clinical reason.")
        else:
            override_record = {
                "patient_id": resolved_patient_id,
                "recommended_esi": esi.get("esi_label"),
                "recommended_esi_level": esi.get("esi_level"),
                "final_nurse_esi": final_esi,
                "decision": decision,
                "reason": reason,
                "high_risk_downgrade": bool(high_risk_downgrade),
                "source_panel": safe_prefix,
                "timestamp": _now_iso(),
            }
            st.session_state["last_override"] = override_record
            st.session_state["override_audit"].append(override_record)

            updated_patient = apply_nurse_override_to_queue(resolved_patient_id, override_record)

            if not updated_patient:
                st.session_state["override_save_notice"] = f"⚠️ Could not find patient {resolved_patient_id} in the Live Queue. Has the queue been cleared?"
                st.rerun()
                return

            audit_details = dict(override_record)
            audit_details.update({
                "queue_status_after_override": updated_patient.get("status"),
                "board_visible_esi_level": updated_patient.get("esi_level"),
                "board_visible_esi_label": updated_patient.get("esi_label"),
                "original_ai_esi_label": updated_patient.get("ai_esi_label"),
                "safety_flag": updated_patient.get("safety_flag"),
            })

            post_audit_event(
                event_type="nurse_acuity_confirmation",
                patient_id=resolved_patient_id,
                action="Nurse saved AI acuity confirmation/override and updated Live Queue",
                details=audit_details,
            )
            st.session_state["override_save_notice"] = (
                f"✅ Nurse decision saved. {resolved_patient_id} is now shown in the Live Queue as {final_esi}."
            )
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def render_engine_explainer():
    st.markdown("""
    ### What changed in this version
    This UI now exposes the ESI engine like a hospital workflow tool, not just a backend rule hidden inside the report.

    **The engine visibly controls:**
    - ESI-1 to ESI-5 acuity recommendation
    - red-flag escalation banners
    - likely ED resources
    - fast-track eligibility
    - reassessment interval
    - nurse accept/override audit behavior
    - live ED waiting-room queue built from submitted patients
    - persistent queue state across browser refreshes while the backend is running
    - persistent nurse/workflow audit trail in the Flask backend
    - final nurse ESI override updates the Live Queue instead of only saving an audit note
    - reassessment/deterioration engine that compares repeat vitals, recalculates ESI, updates the queue, and audits the result
    - high-risk nurse downgrade warning requiring a documented clinical reason
    - patient-level timeline in the detail modal for evaluation, override, reassessment, and queue actions
    """)


render_header()
initialise_patient_queue()
initialise_patient_form_defaults()
st.markdown("---")


# Control Center Sidebar
with st.sidebar:
    st.header("⚙️ Control Center")
    engine_type = st.radio("Decision Engine", [
        "Local Expert System (0 Tokens)",
        "Groq",
        "Google LLM (Gemini)"
    ])

    if engine_type == "Local Expert System (0 Tokens)":
        st.info("Using **Expert System + ESI Acuity Engine (0 Tokens)**")
        selected_llm = "None"
    elif engine_type == "Google LLM (Gemini)":
        st.warning("Using **Google LLM System**")
        selected_llm = st.selectbox("LLM Model for Assessment", [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ])
    else:
        st.success("Using **Groq (Fast Inference)**")
        selected_llm = st.selectbox("LLM Model for Assessment", [
            "llama-3.3-70b-versatile",
            "mixtral-8x7b-32768"
        ])

    st.markdown("---")
    sidebar_spinner_placeholder = st.empty()
    st.subheader("Machine Learning")
    selected_model = st.selectbox("ML Model for Cardiac Risk", ["XGBoost", "Random Forest", "Logistic Regression"])
    st.caption("The ML model estimates cardiac disease probability. The ESI-style acuity engine then applies safety rules and workflow logic.")

    st.markdown("---")
    st.subheader("Data Management")
    dataset_options = [
        "UCI Cleveland Original",
        "Synthetic Global Cohort (10,000 Patients)",
        "High-Risk Elderly Cohort (2,000 Patients)",
        "Global General Population (50,000 Patients)"
    ]

    current_dataset = dataset_options[0]
    try:
        metrics_resp = requests.get(f"{API_URL}/metrics")
        if metrics_resp.status_code == 200:
            current_dataset = metrics_resp.json().get("dataset", dataset_options[0])
    except Exception:
        pass

    idx = dataset_options.index(current_dataset) if current_dataset in dataset_options else 0
    selected_dataset = st.selectbox("Dataset Source", dataset_options, index=idx)

    if selected_dataset != current_dataset:
        with st.spinner(f"Swapping to {selected_dataset} and retraining all models..."):
            requests.post(f"{API_URL}/train", json={"dataset_name": selected_dataset})
        st.rerun()

    st.markdown("---")
    st.subheader("Demo Controls")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Refresh", use_container_width=True, key="sidebar_refresh_queue"):
            st.rerun()
    with c2:
        if st.button("🧹 Clear Queue", use_container_width=True, key="sidebar_reset_system"):
            reset_live_demo_system()
            st.rerun()
    st.caption("Refresh fetches latest data. Clear Queue empties the waiting room.")

st.markdown("---")
queue_col, _ = st.columns([12, 1])
with queue_col:
    st.subheader("🏥 Live Waiting Room Queue")
    render_command_board(st.session_state.get('last_esi'), key_prefix="global_board", show_actions=True)
st.markdown("---")

st.warning("👉 **Select an operations workspace tab below to proceed:**")
tab1, tab_cmd, tab_audit, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 Patient Evaluation",
    "🚦 ESI Command Center",
    "📋 Audit Trail",
    "📈 Model Metrics",
    "🗣️ AI Committee Debate",
    "🗄️ Data Sources",
    "🧠 Explainable AI"
])

with tab1:
    col1, col2 = st.columns([2.5, 1])

    with col2:
        st.subheader("System Dashboard")

        try:
            logs_resp = requests.get(f"{API_URL}/logs")
            if logs_resp.status_code == 200:
                logs = logs_resp.json()
                if engine_type == "Local Expert System (0 Tokens)":
                    total_tokens = sum(
                        log.get('details', {}).get('tokens_used', 0)
                        for log in logs
                        if str(log.get('details', {}).get('engine', '')).startswith("Expert System")
                    )
                else:
                    total_tokens = sum(
                        log.get('details', {}).get('tokens_used', 0)
                        for log in logs
                        if log.get('details', {}).get('engine') == engine_type
                    )
            else:
                total_tokens = 0
                logs = []
        except Exception:
            total_tokens = 0
            logs = []

        st.metric(label="Total Tokens Used", value=total_tokens)

        with st.expander("Transaction Logs"):
            if logs:
                for log in reversed(logs[-10:]):
                    details = log.get('details', {})
                    st.text(f"[{log.get('timestamp', 'unknown')}]")
                    st.text(f"Engine: {details.get('engine')}")
                    st.text(f"Model: {details.get('ml_model')}")
                    if details.get('esi'):
                        st.text(f"ESI: {details['esi'].get('esi_label')}")
                    st.text(f"Tokens: {details.get('tokens_used')}")
                    st.markdown("---")
            else:
                st.text("No transactions yet.")

        with st.expander("Persistent Nurse Audit Trail"):
            render_audit_trail(compact=True)

        with st.expander("System Memory (JSON)"):
            try:
                mem_resp = requests.get(f"{API_URL}/memory")
                if mem_resp.status_code == 200:
                    st.json(mem_resp.json())
            except Exception:
                st.text("Could not load memory.")

        # Pipeline visualization moved to col1

    with col1:
        st.subheader("Patient Vitals & Features")

        c1, c2, c3 = st.columns(3)
        with c1:
            age = st.number_input("Age", min_value=1, max_value=120, key="input_age")
            sex_input = st.selectbox("Sex", ["Male", "Female"], key="input_sex_input")
            sex = 1 if sex_input == "Male" else 0
        with c2:
            trestbps = st.number_input("Systolic BP / Resting BP (mm Hg)", min_value=50, max_value=260, key="input_sbp")
            chol = st.number_input("Cholesterol (mg/dl)", min_value=100, max_value=600, key="input_chol")
        with c3:
            thalach = st.number_input("Heart Rate / Max Heart Rate", min_value=30, max_value=260, key="input_hr")
            fbs_input = st.selectbox("Fasting Blood Sugar > 120", ["No", "Yes"], key="input_fbs_input")
            fbs = 1 if fbs_input == "Yes" else 0

        cp_input = st.selectbox("Cardiac ML Chest Pain Feature (legacy model input)", [
            "No active chest pain / not applicable",
            "1: Typical Angina",
            "2: Atypical Angina",
            "3: Non-anginal Pain",
            "4: Asymptomatic"
        ], key="input_cp_input")
        cp = 4 if cp_input.startswith("No active") else int(cp_input[0])
        st.caption(
            "This field feeds the cardiac ML model only. The ESI triage engine treats chest pain as active "
            "only when the Chief Complaint, clinical notes, or Active chest pain checkbox confirms it."
        )

        st.markdown("### 🚦 ESI-Style Acuity Inputs")
        e1, e2, e3 = st.columns(3)
        with e1:
            chief_complaint = st.selectbox("Chief Complaint", [
                "Chest pain / cardiac symptoms",
                "Shortness of breath",
                "Stroke symptoms",
                "Fever / infection concern",
                "Abdominal pain",
                "Trauma / fall / injury",
                "Allergic reaction",
                "Mental health / overdose concern",
                "Minor injury / laceration",
                "Other"
            ], key="input_chief_complaint")
            active_chest_pain_checkbox = st.checkbox(
                "Active chest pain / cardiac symptoms present",
                help="Check this only when chest pain/cardiac symptoms are part of the current triage complaint.",
                key="input_active_chest_pain_checkbox"
            )
            active_chest_pain = active_chest_pain_checkbox or chief_complaint == "Chest pain / cardiac symptoms"
            temperature_f = st.number_input("Temperature (°F)", min_value=90.0, max_value=110.0, step=0.1, key="input_temperature_f")
        with e2:
            respiratory_rate = st.number_input("Respiratory Rate / min", min_value=4, max_value=60, key="input_respiratory_rate")
            oxygen_saturation = st.number_input("Oxygen Saturation SpO₂ (%)", min_value=50, max_value=100, key="input_oxygen_saturation")
        with e3:
            pain_score = st.slider("Pain Score", min_value=0, max_value=10, key="input_pain_score")
            mental_status = st.selectbox("Mental Status", ["Alert", "Confused/Altered", "Voice/Pain Only", "Unresponsive"], key="input_mental_status")

        e4, e5 = st.columns(2)
        with e4:
            arrival_mode = st.selectbox("Arrival Mode", ["Walk-in", "EMS", "Police/EMS", "Transfer"], key="input_arrival_mode")
            expected_resources = st.multiselect("Expected / likely ED resources", [
                "ECG",
                "Troponin / cardiac labs",
                "CBC/CMP labs",
                "Imaging / X-ray / CT",
                "IV fluids/meds",
                "Respiratory treatment",
                "Specialty consult",
                "Procedure / wound care",
                "Observation / serial reassessment"
            ], key="input_expected_resources")
        with e5:
            st.markdown("**Risk modifiers**")
            immunocompromised = st.checkbox("Immunocompromised", key="input_immunocompromised")
            pregnant = st.checkbox("Pregnant", key="input_pregnant")
            anticoagulants = st.checkbox("On anticoagulants / blood thinners", key="input_anticoagulants")
            suicidal_homicidal = st.checkbox("Suicidal / homicidal / overdose concern", key="input_suicidal_homicidal")
            can_walk = st.checkbox("Can walk / mobilize safely", key="input_can_walk")

        notes = st.text_area(
            "Clinical Notes (Optional)",
            height=120,
            placeholder="Examples: crushing chest pain, shortness of breath, face droop, fever with low BP, fall on blood thinners...",
            key="input_notes"
        )

        st.markdown("<br>", unsafe_allow_html=True)
        if st.session_state.get("form_reset_notice"):
            st.info(st.session_state["form_reset_notice"])
            st.session_state["form_reset_notice"] = None

        eval_col, clear_col = st.columns([2, 1])
        with eval_col:
            evaluate_clicked = st.button(f"Evaluate Patient using {selected_model}", type="primary", use_container_width=True)
        with clear_col:
            st.button("Reset Patient Form", use_container_width=True, on_click=reset_patient_form_inputs, key="clear_patient_form_button")
        st.caption("Reset Patient Form reverts the intake fields to baseline vitals. Use Reset System / Clear Queue in the sidebar to empty the waiting room.")

        st.markdown("---")
        st.subheader("Agent Execution Pipeline")
        
        def _render_pipeline_html(active_index):
            steps = [
                ("ESI Engine", "⚙️"),
                ("Safety Sentinel", "🛡️"),
                ("Analyst Agent", "🔍"),
                ("Reviewer Agent", "⚕️"),
                ("Editor Agent", "📝"),
                ("Documentation", "📄")
            ]
            html = "<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding: 12px; background: rgba(15, 23, 42, 0.6); border-radius: 16px; border: 1px solid rgba(51, 65, 85, 0.5);'>"
            for i, (name, icon) in enumerate(steps):
                if i < active_index:
                    bg = "linear-gradient(135deg, rgba(22, 101, 52, 0.8), rgba(20, 83, 45, 0.8))"
                    border = "rgba(74, 222, 128, 0.6)"
                    color = "#f0fdf4"
                    glow = "box-shadow: 0 0 10px rgba(74, 222, 128, 0.2);"
                    icon_disp = "✅"
                elif i == active_index:
                    bg = "linear-gradient(135deg, rgba(30, 58, 138, 0.9), rgba(30, 64, 175, 0.9))"
                    border = "rgba(96, 165, 250, 0.8)"
                    color = "#ffffff"
                    glow = "box-shadow: 0 0 18px rgba(96, 165, 250, 0.7);"
                    icon_disp = icon
                else:
                    bg = "rgba(30, 41, 59, 0.5)"
                    border = "rgba(51, 65, 85, 0.5)"
                    color = "#94a3b8"
                    glow = ""
                    icon_disp = icon
                    
                html += f"<div style='background: {bg}; border: 1px solid {border}; {glow} padding: 10px 4px; border-radius: 10px; color: {color}; text-align: center; font-size: 0.75rem; font-weight: 800; flex: 1; margin: 0 4px; transition: all 0.4s ease;'>{icon_disp}<br/>{name}</div>"
                if i < len(steps) - 1:
                    arrow_color = "rgba(74, 222, 128, 0.8)" if i < active_index else ("rgba(96, 165, 250, 0.8)" if i == active_index else "rgba(71, 85, 105, 0.6)")
                    html += f"<div style='color: {arrow_color}; font-weight: 900; font-size: 1.1rem;'>➔</div>"
            html += "</div>"
            return html

        pipeline_placeholder = st.empty()
        pipeline_placeholder.markdown(_render_pipeline_html(-1), unsafe_allow_html=True)

        if evaluate_clicked:
            sidebar_spinner_placeholder.markdown("""
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; margin: 15px 0; padding: 15px; border-radius: 5px; background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; font-weight: bold;">
                    <div style="font-size: 32px; animation: hourglass-spin 2s ease-in-out infinite;">⏳</div>
                    <span>System Busy...</span>
                </div>
                <style>
                @keyframes hourglass-spin {
                    0% { transform: rotate(0deg); }
                    50% { transform: rotate(180deg); }
                    100% { transform: rotate(360deg); }
                }
                </style>
            """, unsafe_allow_html=True)
            
            import time
            time.sleep(0.1) # Force Streamlit to flush the UI update before the blocking request
            
            vitals = {
                "age": age,
                "sex": sex,
                "cp": cp,
                "trestbps": trestbps,
                "chol": chol,
                "fbs": fbs,
                "thalach": thalach,
                "chief_complaint": chief_complaint,
                "active_chest_pain": active_chest_pain,
                "cardiac_ml_chest_pain_feature": cp_input,
                "temperature_f": temperature_f,
                "respiratory_rate": respiratory_rate,
                "oxygen_saturation": oxygen_saturation,
                "pain_score": pain_score,
                "mental_status": mental_status,
                "arrival_mode": arrival_mode,
                "expected_resources": expected_resources,
                "immunocompromised": immunocompromised,
                "pregnant": pregnant,
                "anticoagulants": anticoagulants,
                "suicidal_homicidal": suicidal_homicidal,
                "can_walk": can_walk,
            }

            final_data = None

            try:
                response = requests.post(f"{API_URL}/evaluate", json={
                    "session_id": "demo_session",
                    "notes": notes,
                    "engine_type": engine_type,
                    "vitals": vitals,
                    "model_name": selected_model,
                    "llm_model_name": selected_llm,
                    "dataset_name": selected_dataset
                }, stream=True)

                if response.status_code == 200:
                    final_data = {}
                    active_index = 0
                    pipeline_placeholder.markdown(_render_pipeline_html(active_index), unsafe_allow_html=True)
                    
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line.decode('utf-8'))
                            if 'step' in data:
                                step_text = data['step']
                                if "deterministic" in step_text or "ESI" in step_text:
                                    active_index = 0
                                elif "Safety Sentinel" in step_text:
                                    active_index = 1
                                elif "Analyst" in step_text:
                                    active_index = 2
                                elif "Reviewer" in step_text:
                                    active_index = 3
                                elif "Editor" in step_text:
                                    active_index = 4
                                elif "Documentation" in step_text:
                                    active_index = 5
                                pipeline_placeholder.markdown(_render_pipeline_html(active_index), unsafe_allow_html=True)
                            elif 'error' in data:
                                st.error(data['error'])
                                if data.get('esi'):
                                    render_esi_card(data.get('esi'))
                                pipeline_placeholder.markdown("<h5>🔴 Error in Pipeline</h5>", unsafe_allow_html=True)
                                break
                            elif 'done' in data:
                                pipeline_placeholder.markdown(_render_pipeline_html(6), unsafe_allow_html=True)
                                final_data = data
                                break

                    if final_data:
                        st.success("Evaluation Complete!")
                        st.session_state['analyst_draft'] = final_data.get('analyst_draft')
                        st.session_state['reviewer_critique'] = final_data.get('reviewer_critique')
                        st.session_state['last_esi'] = final_data.get('esi')
                        st.session_state['last_report'] = final_data.get('report', '')
                        st.session_state['last_probability'] = final_data.get('disease_probability')
                        st.session_state['last_priority_score'] = final_data.get('priority_score')
                        st.session_state['last_agent_outputs'] = final_data.get('agent_outputs') or {}
                        patient_record = add_patient_to_queue(final_data, vitals, notes)
                        st.session_state['last_patient_id'] = patient_record.get('patient_id')
                        st.session_state['last_patient_record'] = patient_record
                        st.session_state['last_evaluation_complete'] = True
                        st.rerun()
                else:
                    st.error("Error communicating with backend.")
                    pipeline_placeholder.markdown("<h5>🔴 Backend Error</h5>", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Could not reach backend: {e}")
                pipeline_placeholder.markdown("<h5>🔴 Connection Error</h5>", unsafe_allow_html=True)
                
            sidebar_spinner_placeholder.empty()

        st.markdown("---")
        render_latest_evaluation_result_panel()

with tab_cmd:
    st.header("🚦 ESI Command Center")
    render_engine_explainer()
    st.markdown("---")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("Latest Acuity Card")
        render_esi_card(st.session_state.get('last_esi'))
        render_override_panel(st.session_state.get('last_esi'), key_prefix="command_center_latest", patient_id=st.session_state.get("last_patient_id"))
    with c2:
        st.markdown("### 🔁 Deterioration Watch")
        st.info("Implemented: click a patient row, open the reassessment expander, enter repeat vitals, and the app will compare old vs new values, recalculate ESI, update the queue, and write an audit event.")
        if st.session_state.get('last_override'):
            st.markdown("### Last Override / Confirmation")
            st.json(st.session_state['last_override'])

    st.markdown("---")
    render_command_agents(st.session_state.get("last_agent_outputs"), st.session_state.get("patient_queue", []), title="🤖 Visible Command Agents")

with tab_audit:
    st.header("📋 Persistent Nurse / Workflow Audit Trail")
    st.markdown("""
    This tab shows the production-style audit trail for the triage workflow. It records patient queue entry, nurse confirmation/override, escalation, rooming, reassessment, discharge/removal, and queue-clearing events.

    The audit trail is written through the Flask backend to `data/audit_trail.jsonl`, so it survives Streamlit reruns and is separate from the model transaction log.
    """)
    r1, r2 = st.columns([1, 1])
    with r1:
        if st.button("Refresh Audit Trail", use_container_width=True, key="audit_refresh_button"):
            st.rerun()
    with r2:
        st.caption("Newest events are shown first.")
    render_audit_trail(compact=False)


with tab2:
    st.header("Model Performance Comparison")

    st.markdown("""
    ### Evaluation Methodology
    - **Dataset:** UCI Heart Disease Dataset (Processed Cleveland Data).
    - **Data Split:** The dataset is split into an **80% Training Set** and a **20% Test (Holdout) Set**.
    - **Training:** The models (XGBoost, Random Forest, Logistic Regression) are trained exclusively on the 80% Training Set.
    - **Evaluation:** Models predict outcomes for the unseen 20% Test Set. The table below shows Accuracy, Precision, Recall, and F1 Score.
    - **Important:** The ESI-style acuity engine is a deterministic workflow/safety layer. It is not trained by this tab; it uses explicit triage rules layered on top of ML risk.
    """)

    try:
        metrics_resp = requests.get(f"{API_URL}/metrics")
        if metrics_resp.status_code == 200:
            resp_data = metrics_resp.json()
            metrics = resp_data.get("metrics", {})
            st.info(f"Models currently trained on: **{resp_data.get('dataset', 'Unknown')}**")
            if metrics:
                import pandas as pd
                df = pd.DataFrame.from_dict(metrics, orient='index')
                st.dataframe(df.style.format("{:.2%}"), use_container_width=True)
            else:
                st.info("Metrics not available yet. Model may need to be trained.")
    except Exception as e:
        st.error(f"Could not load metrics: {e}")

with tab3:
    st.header("🗣️ Internal AI Committee Debate")
    if 'last_esi' in st.session_state and st.session_state['last_esi']:
        st.markdown("### Deterministic Safety Layer")
        render_esi_card(st.session_state['last_esi'])

    if st.session_state.get("last_agent_outputs"):
        render_command_agents(st.session_state.get("last_agent_outputs"), st.session_state.get("patient_queue", []), title="🤖 Deterministic Command Agents")

    if 'analyst_draft' in st.session_state and st.session_state['analyst_draft']:
        st.markdown("### 1. The Analyst's Initial Draft")
        st.info(st.session_state['analyst_draft'])

        st.markdown("### 2. The Medical Reviewer's Critique")
        st.warning(st.session_state['reviewer_critique'])

        st.markdown("### 3. Chief Editor")
        st.success("The Chief Editor synthesized the above into the final Assessment Report found on the first tab.")
    else:
        st.text("Run a patient evaluation using an LLM to see the internal debate here. Local mode still shows the ESI safety layer.")

with tab4:
    st.header("🗄️ Data Sources")
    st.markdown("""
    ### 1. UCI Cleveland Original (300 Patients)
    - **Source:** [UCI Machine Learning Repository](https://archive.ics.uci.edu/ml/datasets/Heart+Disease)
    - **Description:** The classic Cleveland heart disease dataset. It contains 303 original patient records, with missing rows filtered out. It is the gold standard for introductory cardiac machine learning.

    ### 2. Synthetic Global Cohort (10,000 Patients)
    - **Source:** Dynamically generated locally via statistical modeling.
    - **Description:** This massive dataset is generated on the fly. It uses the statistical distributions of the UCI dataset to construct realistic synthetic patient records.

    ### 3. High-Risk Elderly Cohort (2,000 Patients)
    - **Source:** Dynamically generated via targeted statistical modeling.
    - **Description:** A simulated older demographic with higher baseline blood pressure and cholesterol.

    ### 4. Global General Population (50,000 Patients)
    - **Source:** Dynamically generated via broad statistical modeling.
    - **Description:** A massive simulated younger, healthier general population.

    ### 5. ESI-Style Acuity Engine
    - **Source:** Local deterministic rules in `backend/esi_engine.py`.
    - **Description:** Uses instability triggers, high-risk complaint logic, vital-sign danger zones, expected ED resource count, and cardiac ML probability overlay to recommend ESI-1 through ESI-5.
    - **Purpose:** Makes the app look and behave more like a real ED triage workflow tool instead of only a cardiac-risk calculator.
    """)

with tab5:
    st.header("🧠 Explainable AI (XAI)")
    st.markdown("Understand *why* the ML models make their predictions and see how this patient compares to the dataset.")

    with st.spinner("Loading XAI data..."):
        try:
            xai_resp = requests.post(f"{API_URL}/xai", json={
                "model_name": selected_model,
                "dataset_name": selected_dataset
            })
            if xai_resp.status_code == 200:
                xai_data = xai_resp.json()

                st.subheader(f"1. Feature Importance ({selected_model})")
                st.markdown("This chart shows which vitals the Machine Learning model weights most heavily.")
                importances = xai_data.get("importances", {})
                if importances:
                    import pandas as pd
                    df_imp = pd.DataFrame.from_dict(importances, orient='index', columns=['Importance'])
                    df_imp = df_imp.sort_values(by='Importance', ascending=True)
                    st.bar_chart(df_imp, horizontal=True)
                else:
                    st.info("Feature importance not available for this model.")

                st.markdown("---")
                st.subheader("2. Patient vs. Population (Disease Means)")
                st.markdown("How does the current patient compare to the average patient *who actually has heart disease* in this dataset?")

                means_disease = xai_data.get("means_disease", {})
                if means_disease:
                    c1, c2, c3, c4 = st.columns(4)

                    avg_age = means_disease.get('age', 0)
                    delta_age = age - avg_age
                    c1.metric("Age", f"{age}", delta=f"{delta_age:.1f} vs Avg ({avg_age:.1f})", delta_color="inverse")

                    avg_bp = means_disease.get('trestbps', 0)
                    delta_bp = trestbps - avg_bp
                    c2.metric("Resting BP", f"{trestbps}", delta=f"{delta_bp:.1f} vs Avg ({avg_bp:.1f})", delta_color="inverse")

                    avg_chol = means_disease.get('chol', 0)
                    delta_chol = chol - avg_chol
                    c3.metric("Cholesterol", f"{chol}", delta=f"{delta_chol:.1f} vs Avg ({avg_chol:.1f})", delta_color="inverse")

                    avg_hr = means_disease.get('thalach', 0)
                    delta_hr = thalach - avg_hr
                    c4.metric("Heart Rate", f"{thalach}", delta=f"{delta_hr:.1f} vs Avg ({avg_hr:.1f})")

                st.markdown("---")
                st.subheader("3. Dataset Correlation Matrix")
                st.markdown("This heatmap shows how different vitals are correlated across the entire dataset. A value of 1.0 means perfect correlation.")
                correlations = xai_data.get("correlations", {})
                if correlations:
                    import pandas as pd
                    df_corr = pd.DataFrame.from_dict(correlations)
                    st.dataframe(
                        df_corr.style.background_gradient(cmap='RdBu_r', axis=None, vmin=-1, vmax=1).format("{:.2f}"),
                        use_container_width=True
                    )

        except Exception as e:
            st.error(f"Could not load XAI data: {e}")
