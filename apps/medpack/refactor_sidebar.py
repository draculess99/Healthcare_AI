import os
import re

file_path = r"d:\Work\Springboard\ANTIGRAVITY-SCRATCH\Medicaldeviceproject\medpack_ai\frontend\dashboard.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace Runtime Mode section
old_runtime = """# Sidebar Controls
st.sidebar.header("🧭 Runtime Mode")

backend_options = ["Local Backend", "Remote Backend"]
default_backend_index = 0 if DEFAULT_BACKEND_TARGET not in backend_options else backend_options.index(DEFAULT_BACKEND_TARGET)
backend_target = st.sidebar.radio(
    "Backend target",
    backend_options,
    index=default_backend_index,
    help="Local Backend uses Flask on your Windows laptop. Remote Backend points to a deployed Railway/Render API URL."
)

if backend_target == "Remote Backend":
    remote_url_input = st.sidebar.text_input(
        "Remote API URL",
        value=REMOTE_MEDPACK_API_BASE_URL,
        placeholder="https://your-medpack-backend.up.railway.app",
        help="Use this only after the backend is deployed. Leave blank to avoid accidental remote calls."
    ).strip().rstrip("/")
    MEDPACK_API_BASE_URL = remote_url_input or LOCAL_MEDPACK_API_BASE_URL
    if not remote_url_input:
        st.sidebar.warning("Remote Backend selected but no remote URL is set. Falling back to local backend.")
else:
    MEDPACK_API_BASE_URL = LOCAL_MEDPACK_API_BASE_URL

agent_mode_label = st.sidebar.radio(
    "Agent execution",
    ["Local AI Mode — zero tokens", "Remote LLM Mode — may use tokens"],
    index=0,
    help="Local mode is deterministic and free. Remote LLM mode only uses tokens if the backend has USE_LLM_AGENTS=true and a valid API key."
)
agent_mode = "remote" if agent_mode_label.startswith("Remote") else "local"

if agent_mode == "local":
    st.sidebar.success("Local AI Mode: no LLM/API tokens used.")
    selected_model = None
else:
    st.sidebar.warning("Remote LLM Mode selected. Tokens are only used if the backend is explicitly configured with USE_LLM_AGENTS=true and GEMINI_API_KEY.")
    selected_model = st.sidebar.selectbox(
        "Select Remote Model",
        ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-3.1-flash-lite", "gemini-2.0-flash-exp"],
        index=2
    )

# Render Token Meter
token_gauge_placeholder = st.sidebar.empty()"""

new_runtime = """# Sidebar Controls
with st.sidebar.container(border=True):
    st.subheader("🧭 Runtime Mode")

    backend_options = ["Local Backend", "Remote Backend"]
    default_backend_index = 0 if DEFAULT_BACKEND_TARGET not in backend_options else backend_options.index(DEFAULT_BACKEND_TARGET)
    backend_target = st.radio(
        "Backend target",
        backend_options,
        index=default_backend_index,
        help="Local Backend uses Flask on your Windows laptop. Remote Backend points to a deployed Railway/Render API URL."
    )

    if backend_target == "Remote Backend":
        remote_url_input = st.text_input(
            "Remote API URL",
            value=REMOTE_MEDPACK_API_BASE_URL,
            placeholder="https://your-medpack-backend.up.railway.app",
            help="Use this only after the backend is deployed. Leave blank to avoid accidental remote calls."
        ).strip().rstrip("/")
        MEDPACK_API_BASE_URL = remote_url_input or LOCAL_MEDPACK_API_BASE_URL
        if not remote_url_input:
            st.warning("Remote Backend selected but no remote URL is set. Falling back to local backend.")
    else:
        MEDPACK_API_BASE_URL = LOCAL_MEDPACK_API_BASE_URL

    agent_mode_label = st.radio(
        "Agent execution",
        ["Local AI Mode — zero tokens", "Remote LLM Mode — may use tokens"],
        index=0,
        help="Local mode is deterministic and free. Remote LLM mode only uses tokens if the backend has USE_LLM_AGENTS=true and a valid API key."
    )
    agent_mode = "remote" if agent_mode_label.startswith("Remote") else "local"

    if agent_mode == "local":
        st.success("Local AI Mode: no LLM/API tokens used.")
        selected_model = None
    else:
        st.warning("Remote LLM Mode selected. Tokens are only used if the backend is explicitly configured with USE_LLM_AGENTS=true and GEMINI_API_KEY.")
        selected_model = st.selectbox(
            "Select Remote Model",
            ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-3.1-flash-lite", "gemini-2.0-flash-exp"],
            index=2
        )

    # Render Token Meter
    token_gauge_placeholder = st.empty()"""

content = content.replace(old_runtime, new_runtime)

# Replace Telemetry section
old_telemetry = """st.sidebar.caption(f"Backend API: `{MEDPACK_API_BASE_URL}`")
st.sidebar.markdown("---")
st.sidebar.header("🔧 Scenario Telemetry Controls")

# Options
DEPARTMENTS = [
    "Emergency Department",
    "ICU",
    "Surgery",
    "Med-Surg",
    "Labor and Delivery",
    "Radiology",
    "Outpatient Clinic"
]

ITEMS = {
    "IV Start Kit": "IV Supplies",
    "Syringe 10ml": "IV Supplies",
    "Nitrile Gloves Medium": "PPE",
    "Nitrile Gloves Large": "PPE",
    "Oxygen Mask": "Respiratory",
    "Wound Care Pack": "Wound Care",
    "Foley Catheter Kit": "Catheterization",
    "Blood Draw Kit": "Lab Supplies",
    "PPE Gown": "PPE",
    "Saline Flush": "IV Supplies",
    "Sterile Gauze": "Wound Care",
    "Surgical Tray": "Surgical Supplies",
    "Nasal Cannula": "Respiratory",
    "Patient Monitoring Leads": "Monitoring"
}

dept = st.sidebar.selectbox("Department", DEPARTMENTS, index=0)
item = st.sidebar.selectbox("Supply Item", list(ITEMS.keys()), index=0)
item_cat = ITEMS[item]

st.sidebar.markdown(f"**Category:** `{item_cat}`")

current_stock = st.sidebar.number_input("Current Stock", min_value=0, max_value=500, value=30)
patient_volume = st.sidebar.slider("Patient Volume", 1, 100, 15)
acuity_level = st.sidebar.slider("Acuity Level (1=Low, 4=Critical)", 1.0, 4.0, 2.5, step=0.1)
procedure_count = st.sidebar.slider("Procedure Count", 0, 50, 6)
recent_usage_rate = st.sidebar.slider("Recent Usage Rate (units/hr)", 0.0, 50.0, 8.5, step=0.5)
supplier_delay = st.sidebar.slider("Supplier Delay (Days)", 0.0, 14.0, 2.5, step=0.5)
reorder_point = st.sidebar.number_input("Reorder Point", min_value=0, max_value=200, value=25)
supplier_reliability = st.sidebar.slider("Supplier Reliability Score", 0.0, 1.0, 0.9, step=0.05)
pack_time = st.sidebar.number_input("Pack Time (Minutes)", min_value=1.0, max_value=30.0, value=4.5, step=0.5)
clinical_criticality = st.sidebar.slider("Clinical Criticality (1-4)", 1, 4, 3)

hour = st.sidebar.slider("Hour of Day", 0, 23, 12)
day_of_week = st.sidebar.slider("Day of Week (0=Mon, 6=Sun)", 0, 6, 2)
season = st.sidebar.selectbox("Season", ["Spring", "Summer", "Autumn", "Winter"], index=1)"""

new_telemetry = """st.sidebar.caption(f"Backend API: `{MEDPACK_API_BASE_URL}`")

with st.sidebar.container(border=True):
    st.subheader("🏥 Supply Selection")
    # Options
    DEPARTMENTS = [
        "Emergency Department",
        "ICU",
        "Surgery",
        "Med-Surg",
        "Labor and Delivery",
        "Radiology",
        "Outpatient Clinic"
    ]

    ITEMS = {
        "IV Start Kit": "IV Supplies",
        "Syringe 10ml": "IV Supplies",
        "Nitrile Gloves Medium": "PPE",
        "Nitrile Gloves Large": "PPE",
        "Oxygen Mask": "Respiratory",
        "Wound Care Pack": "Wound Care",
        "Foley Catheter Kit": "Catheterization",
        "Blood Draw Kit": "Lab Supplies",
        "PPE Gown": "PPE",
        "Saline Flush": "IV Supplies",
        "Sterile Gauze": "Wound Care",
        "Surgical Tray": "Surgical Supplies",
        "Nasal Cannula": "Respiratory",
        "Patient Monitoring Leads": "Monitoring"
    }

    dept = st.selectbox("Department", DEPARTMENTS, index=0)
    item = st.selectbox("Supply Item", list(ITEMS.keys()), index=0)
    item_cat = ITEMS[item]
    st.markdown(f"**Category:** `{item_cat}`")

with st.sidebar.container(border=True):
    st.subheader("📊 Operational Metrics")
    current_stock = st.number_input("Current Stock", min_value=0, max_value=500, value=30)
    patient_volume = st.slider("Patient Volume", 1, 100, 15)
    acuity_level = st.slider("Acuity Level (1=Low, 4=Critical)", 1.0, 4.0, 2.5, step=0.1)
    procedure_count = st.slider("Procedure Count", 0, 50, 6)
    recent_usage_rate = st.slider("Recent Usage Rate (units/hr)", 0.0, 50.0, 8.5, step=0.5)

with st.sidebar.container(border=True):
    st.subheader("⏱️ Supply & Logistics")
    supplier_delay = st.slider("Supplier Delay (Days)", 0.0, 14.0, 2.5, step=0.5)
    reorder_point = st.number_input("Reorder Point", min_value=0, max_value=200, value=25)
    supplier_reliability = st.slider("Supplier Reliability Score", 0.0, 1.0, 0.9, step=0.05)
    pack_time = st.number_input("Pack Time (Minutes)", min_value=1.0, max_value=30.0, value=4.5, step=0.5)
    clinical_criticality = st.slider("Clinical Criticality (1-4)", 1, 4, 3)

with st.sidebar.container(border=True):
    st.subheader("📅 Time Context")
    hour = st.slider("Hour of Day", 0, 23, 12)
    day_of_week = st.slider("Day of Week (0=Mon, 6=Sun)", 0, 6, 2)
    season = st.selectbox("Season", ["Spring", "Summer", "Autumn", "Winter"], index=1)"""

content = content.replace(old_telemetry, new_telemetry)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Refactoring complete.")
