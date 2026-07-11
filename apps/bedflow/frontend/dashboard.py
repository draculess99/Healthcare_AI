import os
import streamlit as st
import pandas as pd
import requests
from urllib.parse import urlencode

API_URL = os.getenv("BEDFLOW_API_URL", "http://127.0.0.1:5005/api").rstrip("/")


def auth_headers():
    token = st.session_state.get("auth_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def current_user():
    return st.session_state.get("auth_user") or {}


def user_permissions():
    return set(current_user().get("permissions", []))


def has_permission(permission):
    return permission in user_permissions()


def normalize_owner_role(owner_role):
    aliases = {
        "Pharmacy": "Pharmacist",
        "Utilization Management": "Utilization Manager",
        "Family / Case Manager": "Case Manager",
        "Transport": "Transport Coordinator",
    }
    return aliases.get(owner_role, owner_role)


def can_update_visible_task(task):
    user = current_user()
    permissions = user_permissions()
    if "task.update_any" in permissions:
        return True
    return (
        "task.update_own" in permissions
        and normalize_owner_role(task.get("owner_role")) == user.get("role")
    )

st.set_page_config(page_title="BedFlow AI", layout="wide", initial_sidebar_state="expanded")

# Minimal CSS enhancements (relying on config.toml for primary dark theme)
st.markdown("""
<style>
    /* Metric Cards */
    div[data-testid="metric-container"] {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.85rem !important;
        color: #ff5252 !important;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 4px 4px 0px 0px;
        padding-top: 10px;
        padding-bottom: 10px;
    }

    .command-center-box {
        padding: 1rem 1.25rem;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(255, 255, 255, 0.04);
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏥 BedFlow AI: Hospital Patient-Flow Control Tower")
st.markdown("### *Discharge delay, readmission risk, bed recovery, and human-supervised action planning*")

with st.sidebar:
    st.header("🎛️ Control Panel")

    st.markdown("#### 🔐 Stage 8 Identity")
    if not st.session_state.get("auth_token"):
        try:
            demo_response = requests.get(f"{API_URL}/auth/demo_users", timeout=5)
            demo_payload = demo_response.json() if demo_response.status_code == 200 else {}
            demo_users = demo_payload.get("users", [])
        except requests.RequestException:
            demo_users = []

        if demo_users:
            user_labels = {
                f"{user.get('display_name')} — {user.get('role')}": user
                for user in demo_users
            }
            selected_login = st.selectbox("Demo user", list(user_labels.keys()))
            demo_password = st.text_input(
                "Password",
                value="BedFlowDemo!",
                type="password",
                help="Local demo default. Override with BEDFLOW_DEMO_PASSWORD.",
            )
            if st.button("Sign in", use_container_width=True, type="primary"):
                chosen = user_labels[selected_login]
                try:
                    response = requests.post(
                        f"{API_URL}/auth/login",
                        json={"username": chosen.get("username"), "password": demo_password},
                        timeout=10,
                    )
                    if response.status_code == 200:
                        payload = response.json()
                        st.session_state["auth_token"] = payload.get("token")
                        st.session_state["auth_user"] = payload.get("user")
                        st.success("Signed in.")
                        st.rerun()
                    else:
                        st.error(response.json().get("message", "Sign-in failed."))
                except requests.RequestException as exc:
                    st.error(f"Sign-in unavailable: {exc}")
        else:
            st.warning("Backend identity service is unavailable.")
    else:
        user = current_user()
        st.success(f"{user.get('display_name')} — {user.get('role')}")
        st.caption(user.get("department", ""))
        with st.expander("Permissions", expanded=False):
            for permission in sorted(user_permissions()):
                st.write(f"• `{permission}`")
        if st.button("Sign out", use_container_width=True):
            try:
                requests.post(f"{API_URL}/auth/logout", headers=auth_headers(), timeout=5)
            except requests.RequestException:
                pass
            st.session_state.pop("auth_token", None)
            st.session_state.pop("auth_user", None)
            st.rerun()

    st.divider()
    
    # Token Usage Tracker
    st.session_state.setdefault("total_tokens", 0)
    col1, col2 = st.columns([2.2, 1])
    with col1:
        token_metric_placeholder = st.empty()
        token_metric_placeholder.metric(
            label="Total Tokens Used",
            value=f"{st.session_state['total_tokens']:,}",
            help="Tracks cumulative token usage when using Groq or Gemini LLM."
        )
    with col2:
        st.write("") # spacing alignment
        st.write("") 
        if st.button("🔄 Reset", help="Reset tokens to zero", use_container_width=True):
            st.session_state["total_tokens"] = 0
            st.rerun()
    
    st.write("Global system controls & configuration.")
    st.divider()
    
    # Synchronized Sidebar Spinner
    st.markdown("""
        <style>
        .custom-sync-container {
            display: none;
            text-align: center;
            margin-bottom: 15px;
            padding: 10px;
            background: rgba(255, 82, 82, 0.1);
            border: 1px solid rgba(255, 82, 82, 0.3);
            border-radius: 8px;
        }
        
        .custom-hourglass {
            display: inline-block;
            font-size: 24px;
            animation: hourglass-spin 2s ease-in-out infinite;
        }
        
        .custom-busy-text {
            display: block;
            margin-top: 5px;
            font-size: 14px;
            color: #ff5252;
            font-weight: bold;
        }
        
        @keyframes hourglass-spin {
            0% { transform: rotate(0deg); }
            50% { transform: rotate(180deg); }
            100% { transform: rotate(180deg); }
        }
        
        /* Bind visibility to Streamlit's native running widget using CSS :has() */
        html:has([data-testid="stStatusWidget"]) .custom-sync-container {
            display: block;
        }
        </style>
        <div class="custom-sync-container">
            <span class="custom-hourglass">⏳</span>
            <span class="custom-busy-text">System Busy...</span>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("#### System Operations")
    if st.button(
        "🔄 Refresh / Train Models",
        use_container_width=True,
        disabled=not has_permission("model.train"),
        help="Administrator permission is required.",
    ):
        with st.spinner("Training models..."):
            res = requests.post(f"{API_URL}/train_models", headers=auth_headers(), timeout=120)
            if res.status_code == 200:
                st.success("Models trained and versioned artifacts published successfully.")
            else:
                st.error(f"Training failed: {res.text}")
                
    st.divider()
    st.markdown("#### Settings")
    
    decision_system = st.selectbox(
        "🧠 Decision System", 
        ["Internal Expert System", "Groq", "Gemini LLM"],
        help="Select which system handles the AI arbitration logic. (Groq & Gemini require API keys in .env)"
    )
    
    model_name = None
    if decision_system == "Groq":
        model_name = st.selectbox(
            "⚡ Groq Model",
            ["llama-3.3-70b-versatile", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.6-27b", "groq/compound-mini"]
        )
    elif decision_system == "Gemini LLM":
        model_name = st.selectbox(
            "✨ Gemini Model",
            ["gemini-1.5-pro", "gemini-1.5-flash"]
        )

    st.checkbox("Auto-refresh patient queue", value=True)
    st.selectbox("Default Dashboard View", ["Hospital Command Center", "Unit Level", "Patient Level"])

    st.divider()
    st.markdown("#### Runtime Status")
    try:
        health_response = requests.get(f"{API_URL}/health", timeout=2)
        if health_response.status_code == 200:
            health_payload = health_response.json()
            st.success("Backend connected")
            st.caption(
                f"Version: {health_payload.get('app_version', 'unknown')} · "
                f"Stage: {health_payload.get('upgrade_stage', 'unknown')}"
            )
            st.caption(
                f"Model: {health_payload.get('model_version') or 'not loaded'} · "
                f"Source: {health_payload.get('model_source', 'unknown')}"
            )
            try:
                ready_response = requests.get(f"{API_URL}/ready", timeout=3)
                ready_payload = ready_response.json()
                if ready_payload.get("status") == "ready":
                    st.success("Deployment readiness: ready")
                elif ready_payload.get("ready"):
                    st.warning("Deployment readiness: degraded")
                else:
                    st.error("Deployment readiness: not ready")
            except requests.RequestException:
                st.warning("Readiness probe unavailable")
        else:
            st.warning(f"Backend returned HTTP {health_response.status_code}")
    except requests.RequestException:
        st.warning("Backend is starting or unavailable")
    st.caption(f"API: {API_URL}")


def api_get(path, default):
    try:
        res = requests.get(f"{API_URL}{path}", headers=auth_headers(), timeout=10)
        if res.status_code == 200:
            return res.json()
        return default
    except Exception as e:
        st.error(f"Failed to connect to API: {e}")
        return default


def api_post(path, payload=None):
    return requests.post(f"{API_URL}{path}", json=payload, headers=auth_headers(), timeout=60)


def load_patients():
    return api_get("/demo_patients", [])


def load_hospital_capacity():
    return api_get("/hospital_capacity", {})


def load_discharge_queue(limit=75):
    return api_get(f"/discharge_queue?limit={limit}", [])


def load_discharge_checklist(patient_data, model_outputs=None):
    payload = {"patient_data": patient_data, "model_outputs": model_outputs or {}}
    try:
        res = api_post("/discharge_checklist", payload)
        if res.status_code == 200:
            return res.json()
        st.error(f"Checklist failed: {res.text}")
        return None
    except Exception as e:
        st.error(f"Checklist unavailable: {e}")
        return None


def load_model_explanations(patient_data, model_outputs=None, top_n=5):
    payload = {
        "patient_data": patient_data,
        "model_outputs": model_outputs or {},
        "top_n": top_n,
    }
    try:
        res = api_post("/explain_patient", payload)
        if res.status_code == 200:
            return res.json()
        st.error(f"Explainability failed: {res.text}")
        return None
    except Exception as e:
        st.error(f"Explainability unavailable: {e}")
        return None


def load_model_feature_importance(top_n=12):
    return api_get(f"/model_feature_importance?top_n={top_n}", {})


def load_model_governance():
    return api_get("/model_governance", {})


def load_metrics_history():
    return api_get("/model_metrics_history", [])


def load_model_card():
    return api_get("/model_card", {})


def load_data_sources():
    return api_get("/data_sources", {})


def prepare_public_readmission_data(force=False):
    return api_post("/prepare_readmission_data", {"force": force})


def load_latest_model_artifacts():
    return api_post("/load_latest_model", {})


def build_fhir_export(patient_data, model_outputs=None, checklist=None, tasks=None):
    return api_post("/fhir/bundle", {
        "patient_data": patient_data,
        "model_outputs": model_outputs or {},
        "discharge_checklist": checklist or {},
        "tasks": tasks or [],
    })


def load_task_summary():
    return api_get("/tasks/summary", {})


def load_tasks(patient_id=None, owner=None, status=None, include_completed=True):
    params = {}
    if patient_id:
        params["patient_id"] = patient_id
    if owner and owner != "All":
        params["owner"] = owner
    if status and status != "All":
        params["status"] = status
    if not include_completed:
        params["include_completed"] = "false"
    query = f"?{urlencode(params)}" if params else ""
    return api_get(f"/tasks{query}", [])


def load_overdue_tasks():
    return api_get("/tasks/overdue", [])


def load_task_events(patient_id=None, actor_role=None):
    params = {}
    if patient_id:
        params["patient_id"] = patient_id
    if actor_role and actor_role != "All":
        params["actor_role"] = actor_role
    query = f"?{urlencode(params)}" if params else ""
    return api_get(f"/tasks/events{query}", [])


def download_audit_csv():
    return requests.get(f"{API_URL}/audit/export.csv", headers=auth_headers(), timeout=30)


def load_access_log():
    return api_get("/access_log", [])


def load_readiness():
    return api_get("/ready", {})


def load_system_version():
    return api_get("/system/version", {})


def load_operational_metrics():
    return api_get("/metrics", {})


def load_simulation_capability():
    return api_get("/simulations/capability", {})


def run_capacity_scenario(scenario, save=False):
    return api_post("/simulations/run", {"scenario": scenario, "save": save})


def load_simulation_history(limit=100, actor_role=None):
    params = {"limit": limit}
    if actor_role and actor_role != "All":
        params["actor_role"] = actor_role
    return api_get(f"/simulations?{urlencode(params)}", [])


def download_simulation_csv():
    return requests.get(
        f"{API_URL}/simulations/export.csv",
        headers=auth_headers(),
        timeout=30,
    )


def sync_patient_tasks(patient_data, checklist):
    if not checklist:
        return {"patient_tasks": [], "summary": {}}
    try:
        res = api_post("/tasks/sync", {
            "patient_data": patient_data,
            "discharge_checklist": checklist
        })
        if res.status_code == 200:
            return res.json()
        st.error(f"Task sync failed: {res.text}")
        return {"patient_tasks": [], "summary": {}}
    except Exception as e:
        st.error(f"Task workflow unavailable: {e}")
        return {"patient_tasks": [], "summary": {}}


def update_task_status(task_id, status, note):
    return api_post("/tasks/update_status", {
        "task_id": task_id,
        "status": status,
        "note": note,
    })


def clear_patient_results_if_changed(selected_id):
    previous_id = st.session_state.get("selected_patient_id")
    if previous_id != selected_id:
        st.session_state["selected_patient_id"] = selected_id
        st.session_state.pop("committee_result", None)
        st.session_state.pop("model_outputs", None)
        st.session_state.pop("discharge_checklist", None)
        st.session_state.pop("patient_tasks", None)
        st.session_state.pop("model_explanations", None)


def display_capacity_snapshot(capacity):
    st.subheader("🏥 Hospital Command Center Snapshot")
    st.caption("Simulated/proxy unit capacity enriched with cached patient-level XGBoost risk scores. This is a portfolio demonstration, not a live ADT/bed-management feed.")
    if capacity.get("model_version"):
        st.info(f"Queue scoring model: `{capacity.get('model_version')}` · Source: {capacity.get('prediction_source', 'XGBoost inference')}")

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Beds", capacity.get("total_beds", 0))
    k2.metric("Occupied", capacity.get("occupied_beds", 0), f"{capacity.get('occupancy_percent', 0)}%")
    k3.metric("Open Beds", capacity.get("available_beds", 0), f"{capacity.get('beds_pending_cleaning', 0)} cleaning")
    k4.metric("ED Boarders", capacity.get("ed_boarders", 0))
    k5.metric("Expected Discharges", capacity.get("expected_discharges_today", 0))
    k6.metric("Critical Delay Cases", capacity.get("critical_delay_cases", 0))

    unit_rows = capacity.get("units", [])
    if unit_rows:
        st.markdown("#### Unit Bed Board")
        unit_df = pd.DataFrame(unit_rows)
        unit_df = unit_df[[
            "unit",
            "pressure_level",
            "total_beds",
            "occupied_beds",
            "available_beds",
            "occupancy_percent",
            "pending_discharges",
            "delayed_discharges",
            "ed_boarders",
        ]]
        unit_df = unit_df.rename(columns={
            "unit": "Unit",
            "pressure_level": "Pressure",
            "total_beds": "Beds",
            "occupied_beds": "Occupied",
            "available_beds": "Open",
            "occupancy_percent": "Occupancy %",
            "pending_discharges": "Pending Discharges",
            "delayed_discharges": "Delayed Discharges",
            "ed_boarders": "ED Boarders",
        })
        st.dataframe(unit_df, use_container_width=True, hide_index=True)


def display_discharge_queue(queue):
    st.markdown("#### Prioritized Discharge Review Queue")
    st.caption("Each row is batch-scored by the active saved XGBoost artifacts. The queue is cached for speed and does not retrain the models. It prioritizes review; it does not authorize discharge.")

    if not queue:
        st.info("No discharge queue records available.")
        return None

    queue_df = pd.DataFrame(queue)
    display_cols = [
        "patient_id",
        "unit",
        "case_status",
        "delay_risk_display",
        "delay_probability_display",
        "readmission_risk_display",
        "readmission_probability_display",
        "predicted_delay_hours",
        "primary_bottleneck",
        "owner_role",
        "next_action",
        "bed_recovery_score",
    ]
    display_cols = [column for column in display_cols if column in queue_df.columns]
    view_df = queue_df[display_cols].rename(columns={
        "patient_id": "Patient",
        "unit": "Unit",
        "case_status": "Status",
        "delay_risk_display": "Delay Risk",
        "delay_probability_display": "Delay Prob.",
        "readmission_risk_display": "Readmission Risk",
        "readmission_probability_display": "Readmit Prob.",
        "predicted_delay_hours": "Expected Delay Hrs",
        "primary_bottleneck": "Primary Blocker",
        "owner_role": "Owner",
        "next_action": "Next Action",
        "bed_recovery_score": "Priority Score",
    })
    st.dataframe(view_df.head(30), use_container_width=True, hide_index=True)

    with st.expander("How to read this queue", expanded=False):
        st.markdown("""
- **Delay Risk / Probability:** XGBoost estimate that discharge will be delayed.
- **Readmission Risk / Probability:** XGBoost estimate of 30-day readmission risk.
- **Expected Delay Hrs:** XGBoost regression estimate of likely delay magnitude.
- **Primary Blocker / Owner / Next Action:** operational workflow fields from the patient case.
- **Priority Score:** combines model risk, predicted delay, bed pressure, and blocker severity to rank review order.

A low score means **eligible for routine review**, not automatically approved for discharge.
""")

    queue_options = [
        f"{row['patient_id']} | {row['unit']} | {row['case_status']} | {row['primary_bottleneck']} | score {row['bed_recovery_score']}"
        for row in queue
    ]
    selected_label = st.selectbox(
        "Select patient from command-center queue",
        queue_options,
        help="The queue is sorted by operational bed-recovery priority.",
    )
    return selected_label.split(" | ")[0]


def display_discharge_readiness_checklist(checklist):
    st.markdown("#### ✅ Discharge Readiness Checklist")
    st.caption("Stage 2 upgrade: raw operational flags are converted into a hospital-style discharge checklist with blocker ownership and severity.")

    if not checklist:
        st.info("Checklist is not available for this patient.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Readiness Status", checklist.get("readiness_status", "Unknown"))
    m2.metric("Checklist Complete", f"{checklist.get('completion_percent', 0)}%", f"{checklist.get('completed_count', 0)}/{checklist.get('total_count', 0)}")
    m3.metric("Active Blockers", checklist.get("active_blocker_count", 0))
    m4.metric("Critical / High", f"{checklist.get('critical_blocker_count', 0)} / {checklist.get('high_blocker_count', 0)}")

    summary = checklist.get("readiness_summary", "")
    status = checklist.get("readiness_status", "")
    if status in ["Ready for Discharge"]:
        st.success(summary)
    elif status in ["Almost Ready"]:
        st.info(summary)
    elif status in ["Blocked"]:
        st.warning(summary)
    else:
        st.error(summary)

    blockers = checklist.get("blockers", [])
    if blockers:
        blocker_df = pd.DataFrame(blockers)[[
            "display_status", "item", "owner", "severity", "reason", "recommended_action"
        ]].rename(columns={
            "display_status": "Status",
            "item": "Checklist Item",
            "owner": "Owner",
            "severity": "Severity",
            "reason": "Reason",
            "recommended_action": "Recommended Action",
        })
        st.markdown("##### Active Discharge Blockers")
        st.dataframe(blocker_df, use_container_width=True, hide_index=True)

    checklist_items = checklist.get("checklist", [])
    if checklist_items:
        with st.expander("View full readiness checklist", expanded=False):
            checklist_df = pd.DataFrame(checklist_items)[[
                "display_status", "item", "owner", "severity", "reason", "recommended_action"
            ]].rename(columns={
                "display_status": "Status",
                "item": "Checklist Item",
                "owner": "Owner",
                "severity": "Severity",
                "reason": "Reason",
                "recommended_action": "Recommended Action",
            })
            st.dataframe(checklist_df, use_container_width=True, hide_index=True)

    owner_summary = checklist.get("owner_summary", [])
    if owner_summary:
        with st.expander("Owner workload summary", expanded=False):
            st.dataframe(pd.DataFrame(owner_summary).rename(columns={
                "owner": "Owner", "active_blockers": "Active Blockers"
            }), use_container_width=True, hide_index=True)


def _driver_dataframe(drivers):
    if not drivers:
        return pd.DataFrame()
    df = pd.DataFrame(drivers)
    display_cols = [
        "rank",
        "reason",
        "patient_value",
        "model_importance",
        "signal_type",
        "explanation",
    ]
    display_cols = [col for col in display_cols if col in df.columns]
    return df[display_cols].rename(columns={
        "rank": "Rank",
        "reason": "Risk Driver",
        "patient_value": "Patient Value",
        "model_importance": "Model Importance",
        "signal_type": "Signal Type",
        "explanation": "Why It Matters",
    })


def display_model_explanations(explanations):
    st.markdown("#### 🔍 Model Explainability & Risk Reasons")
    st.caption("Stage 4 upgrade: prediction outputs now include patient-specific risk reasons for auditability and trust.")

    if not explanations:
        st.info("Model explanations are not available yet. Run Evaluate Patient Case first.")
        return

    st.info(explanations.get("plain_english_summary", "No explanation summary was returned."))
    st.caption(explanations.get("explanation_method", ""))

    panels = [
        ("discharge_delay", "Discharge Delay Risk"),
        ("readmission_risk", "30-Day Readmission Risk"),
        ("expected_delay_hours", "Expected Delay Hours"),
    ]
    for key, title in panels:
        payload = explanations.get(key, {})
        with st.expander(f"{title} — {payload.get('prediction', 'No prediction label')}", expanded=(key == "discharge_delay")):
            drivers = payload.get("top_drivers", [])
            if drivers:
                st.dataframe(_driver_dataframe(drivers), use_container_width=True, hide_index=True)
            else:
                st.write("No model drivers were available for this output.")

    with st.expander("Explainability governance note", expanded=False):
        st.write(explanations.get("governance_note", "These explanations are decision-support aids only."))



def display_data_sources_panel(data_sources):
    st.subheader("Stage 6 Data Sources")
    st.caption("Hybrid training upgrade: operational delay models use BedFlow synthetic/proxy data, while readmission risk uses public hospital readmission data transformed into the BedFlow schema.")

    if not data_sources:
        st.info("Data-source provenance is not available yet.")
        return

    strategy = data_sources.get("training_strategy", "")
    if strategy:
        st.info(strategy)

    op = data_sources.get("bedflow_operational_data", {})
    raw = data_sources.get("public_readmission_raw_data", {})
    processed = data_sources.get("public_readmission_training_data", {})

    c1, c2, c3 = st.columns(3)
    c1.metric("BedFlow Operational Rows", op.get("rows", op.get("row_count", 0)))
    c2.metric("Public Raw Rows", raw.get("rows", raw.get("row_count", 0)))
    c3.metric("Processed Readmission Rows", processed.get("rows", processed.get("row_count", 0)))

    p1, p2, p3 = st.columns(3)
    p1.write(f"**Operational data:** `{op.get('path', 'missing')}`")
    p2.write(f"**Raw public data:** `{raw.get('path', 'missing')}`")
    p3.write(f"**Readmission training data:** `{processed.get('path', 'missing')}`")

    if processed.get("exists"):
        rate = processed.get("readmitted_30_days_rate")
        st.success(f"Public readmission training layer is ready. 30-day readmission positive-label rate: {rate}")
    else:
        st.warning("Public readmission training layer has not been prepared yet.")

    with st.expander("Data-source details and limitations", expanded=False):
        st.write(f"**Privacy note:** {data_sources.get('privacy_note', 'No PHI used.')}")
        limitations = data_sources.get("limitations", [])
        for item in limitations:
            st.write(f"- {item}")
        st.json(data_sources)



def display_model_governance_panel(governance):
    st.markdown("#### 🧾 Model Lifecycle & Governance")
    st.caption("Stage 5/6 governance: model artifacts, feature columns, metrics history, data-source provenance, and a model card.")

    if not governance:
        st.info("Model governance metadata is not available yet. Train models to publish artifacts.")
        return

    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Model Status", governance.get("status", "Unknown"))
    g2.metric("Active Source", governance.get("active_source", "Unknown"))
    g3.metric("Feature Count", governance.get("feature_count", 0))
    g4.metric("History Runs", governance.get("metrics_history_count", 0))

    version = governance.get("active_model_version") or "No published version yet"
    st.write(f"**Active model version:** `{version}`")
    dataset = governance.get("dataset", {}) or {}
    if dataset:
        st.write(
            f"**Dataset:** `{dataset.get('path', 'unknown')}` | "
            f"Rows: `{dataset.get('row_count', 'n/a')}` | "
            f"Hash: `{dataset.get('dataset_hash', 'n/a')}`"
        )

    artifact_status = governance.get("artifact_status", {})
    if artifact_status:
        artifact_rows = []
        for name, item in artifact_status.items():
            artifact_rows.append({
                "Artifact": name,
                "Path": item.get("path"),
                "Exists": item.get("exists"),
                "Size KB": item.get("size_kb"),
            })
        st.markdown("##### Artifact Registry")
        st.dataframe(pd.DataFrame(artifact_rows), use_container_width=True, hide_index=True)

    latest = governance.get("latest_history_entry")
    if latest:
        with st.expander("Latest metrics-history entry", expanded=False):
            st.json(latest)

    model_card = load_model_card()
    if model_card and model_card.get("status") == "success":
        with st.expander("Generated model card", expanded=False):
            st.markdown(model_card.get("markdown", ""))

    with st.expander("Governance next steps", expanded=False):
        for step in governance.get("next_governance_steps", []):
            st.write(f"- {step}")


def _format_task_minutes(value):
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return "—"
    if minutes < 0:
        return f"Overdue {abs(minutes)}m"
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h {minutes % 60}m"


def _task_dataframe(tasks):
    if not tasks:
        return pd.DataFrame()
    df = pd.DataFrame(tasks)
    if "minutes_until_due" in df.columns:
        df["Due / SLA"] = df["minutes_until_due"].apply(_format_task_minutes)
    if "minutes_waiting" in df.columns:
        df["Waiting"] = df["minutes_waiting"].apply(_format_task_minutes)
    display_cols = [
        "task_id",
        "patient_id",
        "unit",
        "task_type",
        "owner_role",
        "status",
        "severity",
        "escalation_level",
        "Waiting",
        "Due / SLA",
        "overdue",
        "recommended_action",
    ]
    display_cols = [col for col in display_cols if col in df.columns]
    return df[display_cols].rename(columns={
        "task_id": "Task ID",
        "patient_id": "Patient",
        "unit": "Unit",
        "task_type": "Task",
        "owner_role": "Owner",
        "status": "Status",
        "severity": "Severity",
        "escalation_level": "Escalation",
        "overdue": "Overdue",
        "recommended_action": "Recommended Action",
    })


def display_patient_task_workflow(task_bundle, patient_id):
    st.markdown("#### 🧭 Task Ownership & Escalation Workflow")
    st.caption("Stage 3 upgrade: discharge blockers become owned tasks with status, SLA timers, and escalation flags.")

    tasks = task_bundle.get("patient_tasks", []) if task_bundle else []
    summary = task_bundle.get("summary", {}) if task_bundle else {}
    st.session_state["patient_tasks"] = tasks

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Active Tasks", summary.get("active_tasks", 0))
    t2.metric("Overdue", summary.get("overdue_tasks", 0))
    t3.metric("Escalated", summary.get("escalated_tasks", 0))
    t4.metric("Completed", summary.get("completed_tasks", 0))

    if not tasks:
        st.success("No active discharge-blocker tasks were generated for this patient.")
        return

    st.dataframe(_task_dataframe(tasks), use_container_width=True, hide_index=True)

    active_tasks = [task for task in tasks if task.get("status") != "Completed"]
    permitted_tasks = [task for task in active_tasks if can_update_visible_task(task)]
    if active_tasks and not current_user():
        st.info("Sign in to update workflow tasks. The backend binds each update to the authenticated identity.")
    elif active_tasks and not permitted_tasks:
        st.caption(f"{current_user().get('role')} can view these tasks but cannot update tasks owned by other roles.")
    elif permitted_tasks:
        with st.expander("Update an authorized patient task", expanded=False):
            task_options = {
                f"{task['task_id']} | {task.get('owner_role')} | {task.get('task_type')}": task["task_id"]
                for task in permitted_tasks
            }
            selected_task_label = st.selectbox(
                "Task to update",
                list(task_options.keys()),
                key=f"task_select_{patient_id}",
            )
            new_status = st.selectbox(
                "New status",
                ["Pending", "In Progress", "Blocked", "Escalated", "Completed"],
                key=f"task_status_{patient_id}",
            )
            st.caption(
                f"Update will be attributed to {current_user().get('display_name')} "
                f"({current_user().get('role')})."
            )
            note = st.text_input("Optional task note", key=f"task_note_{patient_id}")
            if st.button("Save Task Update", key=f"task_update_btn_{patient_id}"):
                update_res = update_task_status(task_options[selected_task_label], new_status, note)
                if update_res.status_code == 200:
                    st.success("Task updated and immutable event recorded.")
                    st.rerun()
                else:
                    st.error(f"Task update failed: {update_res.text}")


def display_tasks_and_escalations_tab():
    st.header("Task Ownership & Escalations")
    st.write("This stage turns discharge blockers into operational work items owned by real hospital roles.")

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button(
            "Generate / Refresh Tasks From Demo Patients",
            type="primary",
            use_container_width=True,
            disabled=not has_permission("task.sync"),
            help="Bed Manager or Administrator permission is required.",
        ):
            with st.spinner("Creating tasks from discharge checklist blockers..."):
                res = api_post("/tasks/sync_all", {"limit": 100})
                if res.status_code == 200:
                    data = res.json()
                    st.success(
                        f"Processed {data.get('patients_processed', 0)} patients. "
                        f"Created {data.get('created_count', 0)} new tasks; refreshed {data.get('refreshed_count', 0)}."
                    )
                else:
                    st.error(f"Task generation failed: {res.text}")
    with c2:
        st.caption("Tasks use JSON persistence. Set BEDFLOW_DATA_DIR to a mounted directory (recommended: /data on Railway) to preserve task and audit history across redeployments.")

    summary = load_task_summary()
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Total Tasks", summary.get("total_tasks", 0))
    s2.metric("Active", summary.get("active_tasks", 0))
    s3.metric("Overdue", summary.get("overdue_tasks", 0))
    s4.metric("Escalated", summary.get("escalated_tasks", 0))
    s5.metric("Completed", summary.get("completed_tasks", 0))

    role_rows = summary.get("role_rows", [])
    if role_rows:
        st.markdown("#### Active Workload by Owner")
        st.dataframe(pd.DataFrame(role_rows).rename(columns={
            "owner_role": "Owner",
            "active_tasks": "Active Tasks",
            "overdue_tasks": "Overdue",
            "critical_or_high": "Critical / High",
        }), use_container_width=True, hide_index=True)

    tasks = load_tasks()
    if not tasks:
        st.info("No tasks yet. Generate tasks from demo patients or select a patient in the Control Tower.")
        return

    owners = sorted({task.get("owner_role", "Unknown") for task in tasks})
    statuses = sorted({task.get("status", "Unknown") for task in tasks})
    f1, f2, f3 = st.columns(3)
    owner_filter = f1.selectbox("Filter by owner", ["All"] + owners)
    status_filter = f2.selectbox("Filter by status", ["All"] + statuses)
    include_completed = f3.checkbox("Include completed", value=True)
    filtered_tasks = load_tasks(owner=owner_filter, status=status_filter, include_completed=include_completed)

    st.markdown("#### Hospital Task Queue")
    st.dataframe(_task_dataframe(filtered_tasks), use_container_width=True, hide_index=True)

    overdue = load_overdue_tasks()
    if overdue:
        st.markdown("#### 🚨 Overdue Tasks")
        st.dataframe(_task_dataframe(overdue), use_container_width=True, hide_index=True)


def _simulation_history_rows(runs):
    rows = []
    for run in runs:
        scenario = run.get("scenario") or {}
        actor = run.get("actor") or {}
        summary = run.get("summary") or {}
        rows.append({
            "Simulation": run.get("simulation_id"),
            "Created UTC": run.get("created_at_utc"),
            "Scenario": scenario.get("scenario_name"),
            "Scope": scenario.get("scope_unit"),
            "Reviewer": actor.get("display_name"),
            "Role": actor.get("role"),
            "Changed Patients": summary.get("patients_changed", 0),
            "Improved Patients": summary.get("patients_improved", 0),
            "Potential Beds": summary.get("potential_beds_recovered_from_workflow", 0),
            "Additional Capacity": summary.get("additional_potential_capacity", 0),
            "Delay Hours Removed": summary.get("delay_hours_removed", 0),
            "Potential ED Relief": summary.get("potential_ed_boarder_reduction", 0),
        })
    return rows


def display_capacity_simulator_tab():
    st.header("Capacity What-If Simulator")
    st.write(
        "Stage 9 changes selected operational blocker inputs, re-scores the same "
        "synthetic/proxy patient cohort with the active XGBoost artifacts, and compares "
        "the current and simulated capacity picture."
    )
    st.warning(
        "This is counterfactual decision support—not causal proof, a live hospital forecast, "
        "or permission to discharge patients. Clinical stability and physician sign-off are never auto-cleared."
    )

    capability = load_simulation_capability()
    supported_units = capability.get("supported_units", ["All Units"])
    if capability:
        c1, c2, c3 = st.columns(3)
        c1.metric("Upgrade Stage", capability.get("stage", 9))
        c2.metric("Operational Levers", len(capability.get("operational_levers", [])))
        c3.metric("Protected Safety Fields", len(capability.get("protected_safety_fields", [])))

    user = current_user()
    can_run = has_permission("simulation.run")
    if not user:
        st.info("Sign in as a Bed Manager or Administrator to run and save scenarios.")
    elif can_run:
        st.success(
            f"Scenario will be attributed to {user.get('display_name')} ({user.get('role')})."
        )
    else:
        st.info(
            f"{user.get('role')} may view saved scenario results but cannot run new capacity simulations."
        )

    with st.expander("Configure operational scenario", expanded=True):
        top1, top2, top3 = st.columns(3)
        scenario_name = top1.text_input(
            "Scenario name",
            value="Clear priority discharge blockers",
            key="sim_scenario_name",
        )
        scope_unit = top2.selectbox(
            "Unit scope",
            supported_units,
            key="sim_scope_unit",
        )
        horizon_hours = top3.selectbox(
            "Planning horizon",
            [6, 12, 24, 36, 48, 72],
            index=2,
            format_func=lambda value: f"{value} hours",
            key="sim_horizon",
        )

        st.markdown("##### Operational blocker clearance")
        l1, l2 = st.columns(2)
        pharmacy_pct = l1.slider(
            "Pharmacy MedRec cleared",
            0,
            100,
            50,
            step=10,
            format="%d%%",
            key="sim_pharmacy",
        )
        insurance_pct = l1.slider(
            "Insurance authorizations cleared",
            0,
            100,
            40,
            step=10,
            format="%d%%",
            key="sim_insurance",
        )
        transport_pct = l1.slider(
            "Transport blockers cleared",
            0,
            100,
            50,
            step=10,
            format="%d%%",
            key="sim_transport",
        )
        home_care_pct = l2.slider(
            "Home-care setup cleared",
            0,
            100,
            40,
            step=10,
            format="%d%%",
            key="sim_homecare",
        )
        social_work_pct = l2.slider(
            "Social-work reviews cleared",
            0,
            100,
            25,
            step=5,
            format="%d%%",
            key="sim_socialwork",
        )
        rehab_cleared = l2.number_input(
            "Rehab/SNF placements cleared",
            min_value=0,
            max_value=100,
            value=5,
            step=1,
            key="sim_rehab",
        )

        st.markdown("##### Staffing and physical capacity")
        r1, r2, r3, r4 = st.columns(4)
        extra_case_managers = r1.number_input(
            "Additional case managers",
            min_value=0,
            max_value=20,
            value=1,
            step=1,
            key="sim_case_managers",
        )
        cleaning_released = r2.number_input(
            "Beds released from cleaning",
            min_value=0,
            max_value=50,
            value=2,
            step=1,
            key="sim_cleaning",
        )
        temporary_beds = r3.number_input(
            "Temporary staffed beds",
            min_value=0,
            max_value=50,
            value=0,
            step=1,
            key="sim_temp_beds",
        )
        save_scenario = r4.checkbox(
            "Save scenario",
            value=True,
            disabled=not has_permission("simulation.save"),
            key="sim_save",
        )

        scenario = {
            "scenario_name": scenario_name,
            "scope_unit": scope_unit,
            "horizon_hours": horizon_hours,
            "pharmacy_clearance_percent": pharmacy_pct,
            "insurance_clearance_percent": insurance_pct,
            "transport_clearance_percent": transport_pct,
            "home_care_clearance_percent": home_care_pct,
            "social_work_clearance_percent": social_work_pct,
            "rehab_placements_cleared": int(rehab_cleared),
            "additional_case_managers": int(extra_case_managers),
            "cleaning_beds_released": int(cleaning_released),
            "temporary_beds_opened": int(temporary_beds),
        }

        if st.button(
            "Run Capacity Scenario",
            type="primary",
            use_container_width=True,
            disabled=not can_run,
            help="Bed Manager or Administrator permission is required.",
            key="run_capacity_simulation",
        ):
            with st.spinner("Re-scoring current and counterfactual patient cohorts..."):
                response = run_capacity_scenario(scenario, save=save_scenario)
                if response.status_code == 200:
                    st.session_state["capacity_simulation_result"] = response.json()
                    st.success("Scenario completed" + (" and saved." if save_scenario else "."))
                else:
                    st.error(f"Simulation failed: {response.text}")

    result = st.session_state.get("capacity_simulation_result")
    if result:
        summary = result.get("summary") or {}
        st.divider()
        st.subheader("Scenario Impact")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric(
            "Potential Open Beds",
            summary.get("potential_open_beds", 0),
            summary.get("additional_potential_capacity", 0),
        )
        m2.metric(
            "Workflow Bed Candidates",
            summary.get("potential_beds_recovered_from_workflow", 0),
        )
        m3.metric("Delay Hours Removed", summary.get("delay_hours_removed", 0))
        m4.metric("Patients Improved", summary.get("patients_improved", 0))
        m5.metric(
            "High/Critical Reduced",
            summary.get("high_or_critical_cases_reduced", 0),
        )
        m6.metric(
            "Potential ED Relief",
            summary.get("potential_ed_boarder_reduction", 0),
        )

        before_after = pd.DataFrame([
            {
                "Measure": "Potential expedited-review candidates",
                "Current": summary.get("current_review_candidates", 0),
                "Simulated": summary.get("simulated_review_candidates", 0),
            },
            {
                "Measure": "High/Critical delay cases",
                "Current": summary.get("current_high_or_critical_delay_cases", 0),
                "Simulated": summary.get("simulated_high_or_critical_delay_cases", 0),
            },
            {
                "Measure": "Operational blockers",
                "Current": summary.get("current_operational_blockers", 0),
                "Simulated": summary.get("simulated_operational_blockers", 0),
            },
            {
                "Measure": "Open beds / potential open beds",
                "Current": summary.get("current_open_beds", 0),
                "Simulated": summary.get("potential_open_beds", 0),
            },
            {
                "Measure": "ED boarders / potential remaining",
                "Current": summary.get("current_ed_boarders", 0),
                "Simulated": max(
                    0,
                    summary.get("current_ed_boarders", 0)
                    - summary.get("potential_ed_boarder_reduction", 0),
                ),
            },
        ])
        st.dataframe(before_after, use_container_width=True, hide_index=True)

        b1, b2 = st.columns(2)
        with b1:
            st.markdown("#### Blocker Comparison")
            st.dataframe(
                pd.DataFrame(result.get("blocker_comparison", [])),
                use_container_width=True,
                hide_index=True,
            )
        with b2:
            st.markdown("#### Unit Impact")
            st.dataframe(
                pd.DataFrame(result.get("unit_impacts", [])),
                use_container_width=True,
                hide_index=True,
            )

        patient_impacts = result.get("top_patient_impacts", [])
        if patient_impacts:
            st.markdown("#### Highest-Impact Patient Cases")
            impact_df = pd.DataFrame(patient_impacts)
            if "changes" in impact_df.columns:
                impact_df["changes"] = impact_df["changes"].apply(
                    lambda values: "; ".join(values) if isinstance(values, list) else values
                )
            st.dataframe(impact_df, use_container_width=True, hide_index=True)

        with st.expander("Scenario actions and assumptions", expanded=False):
            st.markdown("##### Applied action counts")
            action_rows = []
            for action, details in (result.get("applied_actions") or {}).items():
                action_rows.append({
                    "Action": action.replace("_", " ").title(),
                    "Eligible": details.get("eligible", 0),
                    "Changed": details.get("changed", 0),
                })
            st.dataframe(pd.DataFrame(action_rows), use_container_width=True, hide_index=True)
            st.markdown("##### Assumptions")
            for assumption in result.get("assumptions", []):
                st.write(f"- {assumption}")

    st.divider()
    st.subheader("Saved Scenario History")
    if not has_permission("simulation.read"):
        st.info("A simulation-enabled authenticated role is required to view saved scenarios.")
    else:
        history = load_simulation_history(limit=100)
        if history:
            history_df = pd.DataFrame(_simulation_history_rows(history))
            st.dataframe(history_df, use_container_width=True, hide_index=True)
            if has_permission("simulation.export"):
                export_response = download_simulation_csv()
                if export_response.status_code == 200:
                    st.download_button(
                        "Download Scenario History CSV",
                        data=export_response.content,
                        file_name="bedflow_simulation_runs.csv",
                        mime="text/csv",
                    )
                else:
                    st.error(f"Scenario export failed: {export_response.text}")
        else:
            st.caption("No saved scenarios yet.")


# Tabs
tabs = st.tabs([
    "Control Tower",
    "Tasks & Escalations",
    "Capacity Simulator",
    "Model Quality & Transparency",
    "Memory & Audit Log",
    "FHIR Interoperability",
    "Data & Limitations",
    "System Operations",
])

# Tab 1: Control Tower (Main Workflow)
with tabs[0]:
    st.header("Discharge Readiness & Bed Recovery")

    patients = load_patients()
    capacity = load_hospital_capacity()
    queue = load_discharge_queue(limit=75)

    if capacity:
        display_capacity_snapshot(capacity)
        st.divider()

    if not patients:
        st.warning("No patients found. Please ensure the backend is running and data is generated.")
    else:
        selected_id_from_queue = display_discharge_queue(queue)
        patient_ids = [p["patient_id"] for p in patients]

        if selected_id_from_queue and selected_id_from_queue in patient_ids:
            selected_id = selected_id_from_queue
        else:
            selected_id = st.selectbox("Select Patient to Review", patient_ids)

        clear_patient_results_if_changed(selected_id)
        patient_data = next((p for p in patients if p["patient_id"] == selected_id), None)

        if patient_data:
            st.divider()
            st.subheader(f"Patient Case Review: {selected_id}")

            col1, col2, col3 = st.columns([1.1, 1, 1])
            with col1:
                st.markdown("#### Patient Context")
                st.write(f"**Age**: {patient_data['age']}")
                st.write(f"**Diagnosis**: {patient_data['diagnosis_group']}")
                st.write(f"**Acuity**: {patient_data['acuity_level']}")
                st.write(f"**Discharge Destination**: {patient_data['discharge_destination']}")
                st.write(f"**Primary Blocker**: {patient_data['primary_discharge_bottleneck']}")
                st.write(f"**Bed Occupancy**: {patient_data['current_bed_occupancy_percent']}%")
                st.write(f"**ED Boarding Count**: {patient_data['ed_boarding_count']}")

            with col2:
                st.markdown("#### Operational Flags")
                st.write(f"**Doctor Signoff Pending**: {patient_data['doctor_signoff_pending']}")
                st.write(f"**Pharmacy MedRec Pending**: {patient_data['pharmacy_med_rec_pending']}")
                st.write(f"**Transport Pending**: {patient_data['transport_pending']}")
                st.write(f"**Insurance Auth Pending**: {patient_data['insurance_authorization_pending']}")
                st.write(f"**Rehab/SNF Placement Pending**: {patient_data['rehab_snf_placement_pending']}")
                st.write(f"**Home Care Setup Pending**: {patient_data['home_care_setup_pending']}")

            with col3:
                st.markdown("#### Run AI Analysis")
                st.write("Click once to run the full patient-level prediction and committee workflow.")
                st.caption("Stage 5: if saved artifacts exist, the backend loads them; otherwise the first run trains and publishes the XGBoost models on demand.")
                if st.button("Evaluate Patient Case", type="primary"):
                    st.session_state["is_evaluating"] = True
                    st.session_state.pop("committee_result", None)
                    st.session_state.pop("model_outputs", None)
                    st.session_state.pop("model_explanations", None)
                    st.rerun()
                
                if st.session_state.get("is_evaluating", False):
                    with st.spinner("Predicting risk metrics..."):
                        # 1. Predict
                        pred_res = api_post("/predict_patient", patient_data)
                        
                    if pred_res.status_code == 200:
                        model_outputs = pred_res.json()
                        st.session_state["model_outputs"] = model_outputs
                        refreshed_checklist = load_discharge_checklist(patient_data, model_outputs)
                        st.session_state["discharge_checklist"] = refreshed_checklist
                        model_explanations = load_model_explanations(patient_data, model_outputs)
                        st.session_state["model_explanations"] = model_explanations

                        # 2. Run Committee
                        comm_payload = {
                            "patient_data": patient_data,
                            "model_outputs": model_outputs,
                            "decision_system": decision_system,
                            "model_name": model_name
                        }
                        
                        if decision_system == "Internal Expert System":
                            with st.spinner("Running Internal Expert System..."):
                                comm_res = api_post("/run_committee", comm_payload)
                                if comm_res.status_code == 200:
                                    result = comm_res.json()
                                    st.session_state["committee_result"] = result
                                else:
                                    st.error(f"Committee failed: {comm_res.text}")
                        else:
                            # Visual Multi-Agent Pipeline
                            status = st.status("Initializing Multi-Agent AI Committee...", expanded=True)
                            
                            status.update(label="⚙️ Preparing Patient Context...", state="running")
                            prep_res = api_post("/agent/prepare", comm_payload)
                            if prep_res.status_code != 200:
                                status.update(label=f"Failed preparation: {prep_res.text}", state="error")
                                st.session_state["is_evaluating"] = False
                                st.stop()
                            context = prep_res.json()
                            
                            agent_payload = {
                                "context": context,
                                "decision_system": decision_system,
                                "model_name": model_name
                            }
                            
                            status.update(label="🩺 Patient Safety Advocate reviewing...", state="running")
                            safety_res = api_post("/agent/safety", agent_payload)
                            safety_data = safety_res.json()
                            st.session_state["total_tokens"] += safety_data.get("token_usage", 0)
                            token_metric_placeholder.metric(label="Total Tokens Used", value=f"{st.session_state['total_tokens']:,}")
                            
                            status.update(label="⏱️ Operations & Flow Manager analyzing...", state="running")
                            ops_res = api_post("/agent/ops", agent_payload)
                            ops_data = ops_res.json()
                            st.session_state["total_tokens"] += ops_data.get("token_usage", 0)
                            token_metric_placeholder.metric(label="Total Tokens Used", value=f"{st.session_state['total_tokens']:,}")
                            
                            status.update(label="⚖️ Clinical Director synthesizing final decision...", state="running")
                            director_payload = {**agent_payload, "safety_arg": safety_data.get("result", ""), "ops_arg": ops_data.get("result", "")}
                            director_res = api_post("/agent/director", director_payload)
                            director_data = director_res.json()
                            st.session_state["total_tokens"] += director_data.get("token_usage", 0)
                            token_metric_placeholder.metric(label="Total Tokens Used", value=f"{st.session_state['total_tokens']:,}")
                            
                            status.update(label="✅ AI Committee Decision Reached", state="complete")
                            
                            # Assemble final result matching expected schema
                            result = {
                                "final_recommendation": director_data.get("result", {}).get("final_recommendation", "Proceed (Error)"),
                                "risk_summary": {
                                    "delay_risk": context["delay_risk"],
                                    "readmission_risk": model_outputs.get("readmission_risk_level", "Low"),
                                    "safety_level": context["safety"]
                                },
                                "primary_bottleneck": patient_data.get("primary_discharge_bottleneck", "None"),
                                "action_plan": director_data.get("result", {}).get("action_plan", []),
                                "bed_capacity_impact": context.get("research_outputs", {}).get("bed_capacity", {}),
                                "discharge_checklist": context.get("discharge_checklist", {}),
                                "human_review_required": True,
                                "memory_insight": context["memory_insight"],
                                "audit_reasoning": director_data.get("result", {}).get("audit_reasoning", ""),
                                "research_outputs": context.get("research_outputs", {}),
                                "retrieved_policy": context.get("retrieved_policy", ""),
                                "token_usage": safety_data.get("token_usage", 0) + ops_data.get("token_usage", 0) + director_data.get("token_usage", 0),
                                "llm_error": director_data.get("error") or safety_data.get("error") or ops_data.get("error"),
                                "debate_transcript": {
                                    "safety_advocate": safety_data.get("result", ""),
                                    "operations_manager": ops_data.get("result", "")
                                }
                            }
                            st.session_state["committee_result"] = result
                            
                            if result.get("token_usage", 0) == 0:
                                st.warning(f"{decision_system} token usage was 0. The request likely failed and fell back to the Expert System. Check the Audit Reasoning below for error details.")
                            
                            if result.get("llm_error"):
                                st.error(f"🚨 **FATAL LLM ERROR (Execution Halted for Screenshot):**\n\n{result['llm_error']}")
                                st.session_state["is_evaluating"] = False
                                st.stop()
                    else:
                        st.error(f"Prediction failed: {pred_res.text}")
                        
                    st.session_state["is_evaluating"] = False
                    st.rerun()

            is_evaluated = "committee_result" in st.session_state and "model_outputs" in st.session_state

            if not is_evaluated:
                # Stage 2: discharge readiness checklist is available before model inference.
                checklist_preview = load_discharge_checklist(patient_data)
                st.session_state["discharge_checklist"] = checklist_preview
                st.divider()
                display_discharge_readiness_checklist(checklist_preview)

                if has_permission("task.sync"):
                    task_bundle = sync_patient_tasks(patient_data, checklist_preview)
                else:
                    existing_tasks = load_tasks(patient_id=selected_id)
                    active_tasks = [task for task in existing_tasks if task.get("status") != "Completed"]
                    task_bundle = {
                        "patient_tasks": existing_tasks,
                        "summary": {
                            "active_tasks": len(active_tasks),
                            "overdue_tasks": sum(1 for task in active_tasks if task.get("overdue")),
                            "escalated_tasks": sum(1 for task in active_tasks if task.get("status") == "Escalated"),
                            "completed_tasks": sum(1 for task in existing_tasks if task.get("status") == "Completed"),
                        },
                    }
                st.divider()
                display_patient_task_workflow(task_bundle, selected_id)
            else:
                # Display Results if available
                res = st.session_state["committee_result"]
                outs = st.session_state["model_outputs"]

                st.divider()
                st.subheader("AI Decision Support Outputs")

                c1, c2, c3 = st.columns(3)
                c1.metric("Discharge Delay Risk", outs["delay_risk_level"], f"{outs['discharge_delay_risk_probability']:.2f} prob")
                c2.metric("Readmission Risk", outs["readmission_risk_level"], f"{outs['readmission_risk_probability']:.2f} prob")
                c3.metric("Expected Delay", f"{outs['predicted_delay_hours']} hrs")

                st.markdown(f"**Primary Bottleneck**: {res['primary_bottleneck']}")
                st.markdown(f"**Bed Capacity Impact**: {res['bed_capacity_impact']['estimated_bed_recovery_value']}")
                if res.get("discharge_checklist"):
                    st.markdown(f"**Checklist used by committee**: {res['discharge_checklist'].get('readiness_status')} — {res['discharge_checklist'].get('completion_percent')}% complete")

                display_model_explanations(st.session_state.get("model_explanations"))
                
                st.info(f"**Memory Insight**: {res['memory_insight']}")
                if res.get('retrieved_policy'):
                    st.info(f"**📖 RAG Policy Retrieved**: {res['retrieved_policy']}")
                st.warning(f"**Audit Reasoning**: {res.get('audit_reasoning', 'N/A')}")
                
                if res.get("llm_error"):
                    st.error(f"🚨 **LLM Evaluation Error:**\n\n{res['llm_error']}")
                
                if res.get("debate_transcript"):
                    with st.expander("🗣️ View AI Committee Debate Transcript", expanded=False):
                        st.markdown("##### 🩺 Patient Safety Advocate")
                        st.write(res["debate_transcript"]["safety_advocate"])
                        st.divider()
                        st.markdown("##### ⏱️ Operations & Flow Manager")
                        st.write(res["debate_transcript"]["operations_manager"])

                st.success(f"**Final Recommendation**: {res['final_recommendation']}")

                st.markdown("**Action Plan:**")
                for act in res['action_plan']:
                    st.write(f"- {act}")

                with st.expander("Research module outputs"):
                    st.json(res["research_outputs"])

                st.divider()
                st.subheader("Authenticated Human Review")
                st.caption("Stage 8 binds the decision to the signed-in identity and enforces allowed actions in the backend.")
                reviewer = current_user()
                if not reviewer:
                    st.warning("Sign in from the sidebar to record a human decision.")
                else:
                    st.info(
                        f"Signed in as **{reviewer.get('display_name')}** · "
                        f"Role: **{reviewer.get('role')}** · Department: {reviewer.get('department')}"
                    )
                    allowed_decisions = reviewer.get("allowed_decisions", [])
                    if not allowed_decisions:
                        st.warning("This role may contribute to owned tasks but cannot record a final committee decision.")
                    else:
                        human_dec = st.selectbox("Permitted action", allowed_decisions)
                        reason_required = human_dec in {"Override", "Escalate to Case Manager", "Hold"}
                        human_note = st.text_area(
                            "Decision rationale" + (" (required)" if reason_required else " (optional)"),
                            help="Override, escalation, and hold decisions require a written reason for the audit trail.",
                        )

                        if st.button("Save Authenticated Decision to Audit Log"):
                            if reason_required and not human_note.strip():
                                st.error("A written reason is required for override, escalation, or hold decisions.")
                            else:
                                audit_payload = {
                                    "patient_id": selected_id,
                                    "patient_data": patient_data,
                                    "model_outputs": outs,
                                    "research_outputs": res["research_outputs"],
                                    "committee_recommendation": res["final_recommendation"],
                                    "human_decision": human_dec,
                                    "human_note": human_note,
                                    # These fields are informational only; the backend uses the signed token identity.
                                    "reviewer_name": reviewer.get("display_name"),
                                    "reviewer_role": reviewer.get("role"),
                                    "memory_insight": res["memory_insight"],
                                    "discharge_checklist": res.get("discharge_checklist") or st.session_state.get("discharge_checklist"),
                                    "task_snapshot": st.session_state.get("patient_tasks", []),
                                    "model_explanations": st.session_state.get("model_explanations")
                                }
                                save_res = api_post("/save_human_decision", audit_payload)
                                if save_res.status_code == 200:
                                    st.success("Authenticated decision saved successfully.")
                                    st.session_state.pop("committee_result", None)
                                    st.session_state.pop("model_outputs", None)
                                    st.session_state.pop("discharge_checklist", None)
                                    st.session_state.pop("patient_tasks", None)
                                    st.session_state.pop("model_explanations", None)
                                    st.rerun()
                                else:
                                    st.error(f"Save failed: {save_res.text}")

# Tab 2: Tasks & Escalations
with tabs[1]:
    display_tasks_and_escalations_tab()

# Tab 3: Capacity What-If Simulator
with tabs[2]:
    display_capacity_simulator_tab()

# Tab 4: Model Quality & Transparency
with tabs[3]:
    st.header("Model Quality, Artifacts & Transparency")
    st.write("This area explains what the three XGBoost models predict, where the saved artifacts are used, and how the current version was evaluated.")

    model_overview = pd.DataFrame([
        {"Output": "Discharge delay risk", "Model": "XGBoost classifier", "Meaning": "Probability that discharge will be delayed"},
        {"Output": "30-day readmission risk", "Model": "XGBoost classifier", "Meaning": "Probability of readmission within 30 days"},
        {"Output": "Expected delay hours", "Model": "XGBoost regressor", "Meaning": "Estimated magnitude of discharge delay"},
    ])
    st.dataframe(model_overview, use_container_width=True, hide_index=True)

    with st.expander("What the saved model artifacts represent", expanded=False):
        st.markdown("""
- `models/*.joblib` are the trained XGBoost models loaded for inference.
- `models/feature_columns.json` preserves the exact input layout expected by the models.
- `models/model_registry.json` identifies the active published model version and data provenance.
- `database/model_metrics.json` is the latest evaluation report; it does not make predictions.
- `database/model_metrics_history.json` tracks evaluation summaries across training runs.
- `models/model_card.md` documents intended use, limitations, and governance notes.
""")

    st.info("Operational delay models use synthetic/proxy BedFlow data. The readmission model uses the included public diabetes hospital encounter dataset transformed into the BedFlow feature schema. All outputs remain decision support only.")

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button(
            "Train & Publish Versioned Models",
            type="primary",
            use_container_width=True,
            disabled=not has_permission("model.train"),
            help="Administrator permission is required.",
        ):
            with st.spinner("Training models and publishing artifacts..."):
                train_res = api_post("/train_models")
                if train_res.status_code == 200:
                    data = train_res.json()
                    version = data.get("governance", {}).get("active_model_version")
                    st.success(f"Models trained and published. Version: {version}")
                else:
                    st.error(f"Training failed: {train_res.text}")
    with b2:
        if st.button(
            "Prepare Public Readmission Data",
            use_container_width=True,
            disabled=not has_permission("model.manage"),
            help="Administrator permission is required.",
        ):
            with st.spinner("Preparing public readmission training layer..."):
                prep_res = prepare_public_readmission_data(force=False)
                if prep_res.status_code == 200:
                    summary = prep_res.json().get("summary", {})
                    st.success(f"Readmission training data ready: {summary.get('rows', 0)} rows")
                else:
                    st.error(f"Preparation failed: {prep_res.text}")

    with b3:
        if st.button(
            "Load Latest Saved Artifacts",
            use_container_width=True,
            disabled=not has_permission("model.manage"),
            help="Administrator permission is required.",
        ):
            with st.spinner("Loading saved model artifacts into backend memory..."):
                load_res = load_latest_model_artifacts()
                if load_res.status_code == 200:
                    st.success(load_res.json().get("message", "Loaded saved model artifacts."))
                else:
                    st.warning(load_res.text)

    data_sources = load_data_sources()
    display_data_sources_panel(data_sources)

    st.divider()
    governance = load_model_governance()
    display_model_governance_panel(governance)

    st.divider()
    metrics = api_get("/model_metrics", None)
    if metrics:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Discharge Delay Risk")
            st.json(metrics.get("discharge_delay", {}))

        with col2:
            st.subheader("Readmission Risk")
            st.json(metrics.get("readmission_risk", {}))

        st.subheader("Expected Delay Hours")
        st.json(metrics.get("expected_delay_hours", {}))

        history = load_metrics_history()
        if history:
            with st.expander("Metrics history", expanded=False):
                history_rows = []
                for item in history:
                    history_rows.append({
                        "Version": item.get("model_version"),
                        "Trained At UTC": item.get("trained_at_utc"),
                        "Dataset Hash": item.get("dataset_hash"),
                        "Feature Count": item.get("feature_count"),
                    })
                st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)

        st.subheader("Global Model Feature Importance")
        importance = load_model_feature_importance(top_n=10)
        if importance:
            st.caption(importance.get("method", "Native XGBoost feature importance."))
            st.write(f"**Feature importance model version:** `{importance.get('model_version')}` | **Loaded from artifact:** `{importance.get('loaded_from_artifact')}`")
            i1, i2, i3 = st.tabs(["Delay Risk", "Readmission Risk", "Delay Hours"])
            with i1:
                st.dataframe(pd.DataFrame(importance.get("discharge_delay", [])), use_container_width=True, hide_index=True)
            with i2:
                st.dataframe(pd.DataFrame(importance.get("readmission_risk", [])), use_container_width=True, hide_index=True)
            with i3:
                st.dataframe(pd.DataFrame(importance.get("expected_delay_hours", [])), use_container_width=True, hide_index=True)
    else:
        st.write("No metrics available. Train and publish models first.")

# Tab 5: Memory & Audit Log
with tabs[4]:
    st.header("Authenticated Audit, Task Events & System Memory")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Current State")
        mem = api_get("/memory_state", None)
        if mem:
            st.json(mem)
        else:
            st.write("Failed to load memory state")

    with col2:
        st.subheader("Decision Audit Log")
        if not has_permission("audit.read"):
            st.info("Sign in with an audit-enabled role to view decision records.")
        else:
            logs = api_get("/audit_log", [])
            if logs:
                audit_rows = []
                for log in reversed(logs):
                    audit_rows.append({
                        "Audit ID": log.get("audit_id", "Legacy"),
                        "Timestamp UTC": log.get("timestamp_utc") or log.get("timestamp"),
                        "Patient": log.get("patient_id"),
                        "Reviewer": log.get("reviewer_name", "Legacy record"),
                        "Role": log.get("reviewer_role", "Unknown"),
                        "AI Recommendation": log.get("committee_recommendation"),
                        "Human Decision": log.get("human_decision"),
                        "Rationale": log.get("human_note", ""),
                        "Model Version": log.get("model_version", "Unknown"),
                    })
                audit_df = pd.DataFrame(audit_rows)
                f1, f2, f3 = st.columns(3)
                role_options = ["All"] + sorted([role for role in audit_df["Role"].dropna().unique().tolist() if role])
                role_filter = f1.selectbox("Role", role_options, key="audit_role_filter")
                decision_options = ["All"] + sorted([value for value in audit_df["Human Decision"].dropna().unique().tolist() if value])
                decision_filter = f2.selectbox("Decision", decision_options, key="audit_decision_filter")
                patient_filter = f3.text_input("Patient contains", key="audit_patient_filter")
                if role_filter != "All":
                    audit_df = audit_df[audit_df["Role"] == role_filter]
                if decision_filter != "All":
                    audit_df = audit_df[audit_df["Human Decision"] == decision_filter]
                if patient_filter.strip():
                    audit_df = audit_df[audit_df["Patient"].astype(str).str.contains(patient_filter.strip(), case=False)]
                st.dataframe(audit_df, use_container_width=True, hide_index=True)

                if has_permission("audit.export"):
                    export_response = download_audit_csv()
                    if export_response.status_code == 200:
                        st.download_button(
                            "Download administrator audit CSV",
                            data=export_response.content,
                            file_name="bedflow_audit_export.csv",
                            mime="text/csv",
                        )
                    else:
                        st.error(f"Audit export failed: {export_response.text}")
            else:
                st.write("No audit records yet.")

    st.divider()
    st.subheader("Immutable Task Event History")
    if has_permission("audit.read"):
        events = load_task_events()
        if events:
            event_df = pd.DataFrame(events)
            event_columns = [
                "timestamp_utc", "event_id", "patient_id", "task_id", "task_type",
                "owner_role", "old_status", "new_status", "actor_name", "actor_role", "note"
            ]
            event_columns = [column for column in event_columns if column in event_df.columns]
            st.dataframe(event_df[event_columns], use_container_width=True, hide_index=True)
        else:
            st.caption("Task events will appear after tasks are created or updated.")
    else:
        st.info("Audit permission is required to view task history.")

    if has_permission("access.read"):
        with st.expander("Administrator access log", expanded=False):
            access_events = load_access_log()
            if access_events:
                st.dataframe(pd.DataFrame(list(reversed(access_events))), use_container_width=True, hide_index=True)
            else:
                st.caption("No access events recorded yet.")

# Tab 6: FHIR Interoperability
with tabs[5]:
    st.header("FHIR-Style Interoperability Export")
    st.write("Stage 7 maps a selected BedFlow case into de-identified FHIR R4-shaped Patient, Encounter, Observation, Task, CarePlan, Location, and Bundle resources. This is an export adapter for demonstration—not a certified FHIR server.")
    capability = api_get("/fhir/capability", {})
    if capability:
        c1, c2, c3 = st.columns(3)
        c1.metric("FHIR Shape", capability.get("fhir_version", "R4"))
        c2.metric("Supported Resources", len(capability.get("resources", [])))
        c3.metric("Integration Mode", "Export only")

    fhir_patients = load_patients()
    if not fhir_patients:
        st.warning("No demo patients are available.")
    else:
        fhir_ids = [p.get("patient_id") for p in fhir_patients]
        default_id = st.session_state.get("selected_patient_id")
        default_index = fhir_ids.index(default_id) if default_id in fhir_ids else 0
        fhir_selected = st.selectbox("Patient for FHIR export", fhir_ids, index=default_index, key="fhir_patient")
        fhir_patient = next(p for p in fhir_patients if p.get("patient_id") == fhir_selected)
        fhir_checklist = load_discharge_checklist(fhir_patient) or {}
        fhir_tasks = load_tasks(patient_id=fhir_selected)
        include_predictions = st.checkbox(
            "Include current model predictions as Observation resources",
            value=True,
            help="Runs the saved BedFlow models for this synthetic/proxy patient before building the export bundle.",
        )
        if st.button("Generate FHIR Bundle", type="primary"):
            with st.spinner("Mapping BedFlow case to FHIR-style resources..."):
                fhir_outputs = {}
                if include_predictions:
                    prediction_response = api_post("/predict_patient", fhir_patient)
                    if prediction_response.status_code == 200:
                        fhir_outputs = prediction_response.json()
                    else:
                        st.warning("The bundle will be generated without model-risk observations because prediction failed.")
                result = build_fhir_export(
                    fhir_patient,
                    model_outputs=fhir_outputs,
                    checklist=fhir_checklist,
                    tasks=fhir_tasks,
                )
                if result.status_code == 200:
                    payload = result.json()
                    st.session_state["fhir_bundle"] = payload.get("bundle")
                    st.session_state["fhir_summary"] = payload.get("summary")
                else:
                    st.error(result.text)
        if st.session_state.get("fhir_bundle"):
            summary = st.session_state.get("fhir_summary", {})
            st.success(f"Generated {summary.get('resource_count', 0)} resources in bundle {summary.get('bundle_id', '')}.")
            st.json(summary.get("resource_types", {}))
            st.download_button(
                "Download FHIR Bundle JSON",
                data=__import__("json").dumps(st.session_state["fhir_bundle"], indent=2),
                file_name=f"bedflow_fhir_{fhir_selected}.json",
                mime="application/fhir+json",
            )
            with st.expander("Preview FHIR Bundle", expanded=False):
                st.json(st.session_state["fhir_bundle"])

# Tab 7: Limitations
with tabs[6]:
    st.header("Data Sources and Limitations")
    st.write("""
    **Data Sources & Capabilities**:
    - The discharge delay and capacity models use **synthetic/proxy operational data**.
    - The readmission risk model trains on **publicly available hospital readmission data** mapped into the BedFlow schema.
    - The AI Committee utilizes a **Retrieval-Augmented Generation (RAG)** pipeline to actively search and cite simulated Hospital Standard Operating Procedures (SOPs) and policies.
    - The FHIR Interoperability export transforms these cases into **FHIR R4-shaped** resources for external system integration.
    - **No Protected Health Information (PHI)** or real, identifiable patient records are ever used in this system.

    **Important Notice & Limitations**:
    - The command-center bed board, discharge readiness checklist, and task workflows are operational proxies built for demonstration.
    - The predictive models are not validated clinical models.
    - The Multi-Agent AI committee (Patient Safety Advocate, Operations Manager, Clinical Director) provides **decision support only**.
    - The system **does not automatically discharge patients**. Human review and sign-off are strictly required before any action is taken.
    """)

# Tab 8: Stage 10A System Operations
with tabs[7]:
    st.header("Stage 10A — System Operations & Readiness")
    st.caption(
        "Lightweight production diagnostics for the portfolio deployment: liveness, "
        "deep readiness checks, request IDs, timing, structured logs, and in-process metrics."
    )

    version_payload = load_system_version()
    readiness_payload = load_readiness()

    if version_payload:
        v1, v2, v3 = st.columns(3)
        v1.metric("Application Version", version_payload.get("app_version", "Unknown"))
        v2.metric("Upgrade Stage", version_payload.get("upgrade_stage", "Unknown"))
        completed = version_payload.get("completed_stages", [])
        v3.metric("Completed Increments", len(completed))

    if readiness_payload:
        status = readiness_payload.get("status", "unknown")
        if status == "ready":
            st.success("The API is ready to serve the demonstration workload.")
        elif readiness_payload.get("ready"):
            st.warning("The API can run, but production-readiness warnings remain.")
        else:
            st.error("One or more critical readiness checks failed.")

        summary = readiness_payload.get("summary", {})
        r1, r2, r3 = st.columns(3)
        r1.metric("Checks Passed", summary.get("passed", 0))
        r2.metric("Warnings", summary.get("warnings", 0))
        r3.metric("Critical Failures", summary.get("failed", 0))

        checks = readiness_payload.get("checks", [])
        if checks:
            st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)
    else:
        st.warning("Readiness information is unavailable.")

    st.divider()
    st.subheader("Request Metrics")
    if has_permission("access.read"):
        metrics_payload = load_operational_metrics()
        if metrics_payload:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Requests", metrics_payload.get("total_requests", 0))
            m2.metric("Server Errors", metrics_payload.get("total_server_errors", 0))
            m3.metric("Average Latency", f"{metrics_payload.get('average_latency_ms', 0)} ms")
            m4.metric("Maximum Latency", f"{metrics_payload.get('max_latency_ms', 0)} ms")

            st.markdown("#### HTTP Status Counts")
            st.json(metrics_payload.get("status_counts", {}))
            st.markdown("#### Most-used API Endpoints")
            endpoint_counts = metrics_payload.get("endpoint_counts", {})
            if endpoint_counts:
                endpoint_df = pd.DataFrame(
                    [{"endpoint": key, "requests": value} for key, value in endpoint_counts.items()]
                )
                st.dataframe(endpoint_df, use_container_width=True, hide_index=True)
            if metrics_payload.get("last_error"):
                st.markdown("#### Most Recent Server Error")
                st.json(metrics_payload.get("last_error"))
            st.caption(metrics_payload.get("metrics_scope", ""))
        else:
            st.info("No request metrics are available yet.")
    else:
        st.info("Administrator access is required to view operational request metrics.")

    st.info(
        "Stage 10A observability is a deployment baseline. The next production increment is "
        "transactional PostgreSQL persistence; the current JSON stores remain suitable only "
        "for a local or single-user demonstration."
    )

