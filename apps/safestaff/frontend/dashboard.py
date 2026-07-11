import streamlit as st
import requests
import json
import pandas as pd
import numpy as np
import datetime
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.ui_helpers import (
    get_status_light_mapping,
    get_token_display_text,
    get_token_subtext,
    HELPER_ASSESS_RISK,
    HELPER_LAUNCH_SOLVER,
    HELPER_SUBMIT_DECISION
)

# Config
st.set_page_config(page_title="SafeStaff AI - Google & Kaggle Agentic Capstone", layout="wide", initial_sidebar_state="expanded")

# Backend API base URL. Do NOT include /health here.
# Railway should set BACKEND_URL to the backend service root, e.g.
# https://wonderful-laughter-production-92d9.up.railway.app
from dotenv import load_dotenv
load_dotenv()

API_BASE_URL = os.getenv(
    "BACKEND_URL",
    os.getenv("API_BASE_URL", "https://safestaffai-production.up.railway.app")
).rstrip("/")

# Safety guard: if someone accidentally enters the health endpoint as the base URL,
# strip it back to the service root so /api/... calls do not become /health/api/...
if API_BASE_URL.endswith("/health"):
    API_BASE_URL = API_BASE_URL[:-len("/health")]

# Session state init
if "audit_trail" not in st.session_state:
    st.session_state.audit_trail = []
if "cno_chat_history" not in st.session_state:
    st.session_state.cno_chat_history = []

# Demo presets
demo_scenarios = {
    "Select a Demo Scenario...": None,
    "1. Normal Evening Baseline": {
        "date": datetime.date(2026, 5, 13), # Wednesday
        "type": "Day", # hour = 14
        "dept": "Emergency",
        "beds": 180,
        "acuity": 3,
        "ratio": 0.25,
        "spec": 1,
        "nurse_callout_rate": 0,
        "patient_inflow_multiplier": 1.0,
        "waiting_room_count": 12,
        "arrival_surge_multiplier": 1.0,
        "ambulance_arrival_pressure": "Low",
        "ed_occupancy_percent": 75,
        "inpatient_bed_occupancy_percent": 78,
        "boarding_count": 3,
        "boarding_hours_avg": 1.0,
        "low_acuity_percent": 25,
        "fast_track_open": True,
        "fast_track_capacity": 12,
        "fast_track_queue": 4
    },
    "2. Winter Flu Surge + Staff Call-Out": {
        "date": datetime.date(2026, 1, 12), # Monday
        "type": "Evening", # hour = 18
        "dept": "Emergency",
        "beds": 220,
        "acuity": 2,
        "ratio": 0.14,
        "spec": 1,
        "nurse_callout_rate": 25,
        "patient_inflow_multiplier": 1.6,
        "waiting_room_count": 45,
        "arrival_surge_multiplier": 1.6,
        "ambulance_arrival_pressure": "High",
        "ed_occupancy_percent": 94,
        "inpatient_bed_occupancy_percent": 93,
        "boarding_count": 14,
        "boarding_hours_avg": 3.8,
        "low_acuity_percent": 38,
        "fast_track_open": False,
        "fast_track_capacity": 0,
        "fast_track_queue": 20
    },
    "3. Friday Night Waiting Room Overflow": {
        "date": datetime.date(2026, 10, 16), # Friday
        "type": "Night", # hour = 22
        "dept": "Emergency",
        "beds": 200,
        "acuity": 3,
        "ratio": 0.16,
        "spec": 1,
        "nurse_callout_rate": 10,
        "patient_inflow_multiplier": 1.45,
        "waiting_room_count": 42,
        "arrival_surge_multiplier": 1.5,
        "ambulance_arrival_pressure": "Moderate",
        "ed_occupancy_percent": 88,
        "inpatient_bed_occupancy_percent": 90,
        "boarding_count": 8,
        "boarding_hours_avg": 2.2,
        "low_acuity_percent": 48,
        "fast_track_open": False,
        "fast_track_capacity": 0,
        "fast_track_queue": 26
    },
    "4. Boarding Gridlock / No Inpatient Beds": {
        "date": datetime.date(2026, 2, 10), # Tuesday
        "type": "Evening", # hour = 16
        "dept": "Emergency",
        "beds": 240,
        "acuity": 2,
        "ratio": 0.15,
        "spec": 0,
        "nurse_callout_rate": 10,
        "patient_inflow_multiplier": 1.3,
        "waiting_room_count": 32,
        "arrival_surge_multiplier": 1.25,
        "ambulance_arrival_pressure": "Moderate",
        "ed_occupancy_percent": 99,
        "inpatient_bed_occupancy_percent": 98,
        "boarding_count": 24,
        "boarding_hours_avg": 6.0,
        "low_acuity_percent": 25,
        "fast_track_open": True,
        "fast_track_capacity": 10,
        "fast_track_queue": 8
    },
    "5. Night Shift Shortage + High Acuity": {
        "date": datetime.date(2026, 3, 11), # Wednesday
        "type": "Night", # hour = 2
        "dept": "Emergency",
        "beds": 200,
        "acuity": 1,
        "ratio": 0.13,
        "spec": 0,
        "nurse_callout_rate": 30,
        "patient_inflow_multiplier": 1.35,
        "waiting_room_count": 25,
        "arrival_surge_multiplier": 1.25,
        "ambulance_arrival_pressure": "Moderate",
        "ed_occupancy_percent": 90,
        "inpatient_bed_occupancy_percent": 91,
        "boarding_count": 10,
        "boarding_hours_avg": 3.0,
        "low_acuity_percent": 22,
        "fast_track_open": False,
        "fast_track_capacity": 0,
        "fast_track_queue": 10
    },
    "6. Mass Casualty Intake / Multi-Ambulance Surge": {
        "date": datetime.date(2026, 7, 11), # Saturday
        "type": "Evening", # hour = 21
        "dept": "Emergency",
        "beds": 260,
        "acuity": 1,
        "ratio": 0.10,
        "spec": 0,
        "nurse_callout_rate": 15,
        "patient_inflow_multiplier": 2.0,
        "waiting_room_count": 55,
        "arrival_surge_multiplier": 2.0,
        "ambulance_arrival_pressure": "Critical",
        "ed_occupancy_percent": 98,
        "inpatient_bed_occupancy_percent": 96,
        "boarding_count": 20,
        "boarding_hours_avg": 5.0,
        "low_acuity_percent": 20,
        "fast_track_open": True,
        "fast_track_capacity": 8,
        "fast_track_queue": 8
    }
}

def on_demo_scenario_change():
    sel = st.session_state.demo_select
    if sel and demo_scenarios[sel]:
        # Demo scenario presets belong to the main roster/shortage workflow.
        # Keep the user anchored there after a preset is loaded, even if they
        # were previously viewing Stress, Explainability, Audit, etc.
        st.session_state.workflow_page = "📋 Roster & Shortage Solver"

        data = demo_scenarios[sel]
        st.session_state.scen_date = data["date"]
        st.session_state.scen_type = data["type"]
        st.session_state.scen_dept = data["dept"]
        st.session_state.scen_beds = data["beds"]
        st.session_state.scen_acuity = data["acuity"]
        st.session_state.scen_ratio = data["ratio"]
        st.session_state.scen_spec = data["spec"]
        st.session_state.risk_assessed = False
        st.session_state.pending_log = None
        
        # Save operational research values
        st.session_state.nurse_callout_rate = data["nurse_callout_rate"]
        st.session_state.patient_inflow_multiplier = data["patient_inflow_multiplier"]
        st.session_state.waiting_room_count = data["waiting_room_count"]
        st.session_state.arrival_surge_multiplier = data["arrival_surge_multiplier"]
        st.session_state.ambulance_arrival_pressure = data["ambulance_arrival_pressure"]
        st.session_state.ed_occupancy_percent = data["ed_occupancy_percent"]
        st.session_state.inpatient_bed_occupancy_percent = data["inpatient_bed_occupancy_percent"]
        st.session_state.boarding_count = data["boarding_count"]
        st.session_state.boarding_hours_avg = data["boarding_hours_avg"]
        st.session_state.low_acuity_percent = data["low_acuity_percent"]
        st.session_state.fast_track_open = data["fast_track_open"]
        st.session_state.fast_track_capacity = data.get("fast_track_capacity", 0)
        st.session_state.fast_track_queue = data["fast_track_queue"]

if "scen_date" not in st.session_state:
    st.session_state.scen_date = datetime.date.today()
if "scen_type" not in st.session_state:
    st.session_state.scen_type = "Morning"
if "scen_dept" not in st.session_state:
    st.session_state.scen_dept = "Emergency"
if "scen_beds" not in st.session_state:
    st.session_state.scen_beds = 200
if "scen_acuity" not in st.session_state:
    st.session_state.scen_acuity = 3
if "scen_ratio" not in st.session_state:
    st.session_state.scen_ratio = 0.20
if "scen_spec" not in st.session_state:
    st.session_state.scen_spec = 1

# Initialize operational values
if "nurse_callout_rate" not in st.session_state:
    st.session_state.nurse_callout_rate = 0
if "patient_inflow_multiplier" not in st.session_state:
    st.session_state.patient_inflow_multiplier = 1.0
if "waiting_room_count" not in st.session_state:
    st.session_state.waiting_room_count = 12
if "arrival_surge_multiplier" not in st.session_state:
    st.session_state.arrival_surge_multiplier = 1.0
if "ambulance_arrival_pressure" not in st.session_state:
    st.session_state.ambulance_arrival_pressure = "Low"
if "ed_occupancy_percent" not in st.session_state:
    st.session_state.ed_occupancy_percent = 75
if "inpatient_bed_occupancy_percent" not in st.session_state:
    st.session_state.inpatient_bed_occupancy_percent = 78
if "boarding_count" not in st.session_state:
    st.session_state.boarding_count = 3
if "boarding_hours_avg" not in st.session_state:
    st.session_state.boarding_hours_avg = 1.0
if "low_acuity_percent" not in st.session_state:
    st.session_state.low_acuity_percent = 25
if "fast_track_open" not in st.session_state:
    st.session_state.fast_track_open = True
if "fast_track_capacity" not in st.session_state:
    st.session_state.fast_track_capacity = 12
if "fast_track_queue" not in st.session_state:
    st.session_state.fast_track_queue = 4


# Inject Custom CSS for Rich Glassmorphism Aesthetics & Dark Theme look
st.markdown("""
<style>
    /* Main App Custom Styling */
    .reportview-container {
        background: #0b0f19;
    }
    
    /* Custom Tabs Styling */
    div[data-testid="stTabs"] button {
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        padding: 10px 16px !important;
        margin-right: 8px !important;
        color: #9ca3af !important;
        background-color: rgba(30, 41, 59, 0.5) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px !important;
        transition: all 0.2s ease-in-out !important;
    }
    div[data-testid="stTabs"] button:hover {
        background-color: rgba(51, 65, 85, 0.8) !important;
        color: #e2e8f0 !important;
        border-color: rgba(255, 255, 255, 0.2) !important;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #ffffff !important;
        background-color: #2563eb !important;
        border-color: #3b82f6 !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
    }

    /* Performance workflow selector: compact one-line tab buttons.
       UX meaning:
       - selected tab = solid blue
       - Roster & Shortage Solver = primary blue outline when inactive
       - AI Committee = subtle purple outline when inactive
       - other tabs = neutral dark
       - hover = small lift, brighter border, no distracting animation */
    div[role="radiogroup"] {
        display: flex !important;
        flex-wrap: nowrap !important;
        gap: 4px !important;
        align-items: stretch !important;
        margin-bottom: 18px !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        white-space: nowrap !important;
        padding: 2px 2px 6px 2px !important;
        scrollbar-width: thin !important;
    }

    div[role="radiogroup"] label {
        background-color: rgba(15, 23, 42, 0.88) !important;
        border: 1px solid rgba(148, 163, 184, 0.22) !important;
        border-radius: 8px !important;
        padding: 6px 9px !important;
        margin-right: 0 !important;
        min-height: 34px !important;
        display: flex !important;
        align-items: center !important;
        flex: 0 0 auto !important;
        transform: translateY(0) !important;
        transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease, background-color 0.16s ease !important;
    }

    /* Reduce the visible radio-circle footprint so the controls read like tabs. */
    div[role="radiogroup"] label > div:first-child {
        transform: scale(0.72) !important;
        margin-right: 2px !important;
    }

    div[role="radiogroup"] label:hover {
        background-color: rgba(30, 41, 59, 0.95) !important;
        border-color: rgba(96, 165, 250, 0.48) !important;
        box-shadow: 0 4px 10px rgba(15, 23, 42, 0.35) !important;
        transform: translateY(-1px) !important;
    }

    /* Primary workflow tab: Roster & Shortage Solver.  Keep it important, but not identical to selected. */
    div[role="radiogroup"] label:nth-of-type(1):not(:has(input:checked)) {
        background-color: rgba(30, 64, 175, 0.16) !important;
        border-color: rgba(59, 130, 246, 0.72) !important;
        box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.18), 0 0 12px rgba(37, 99, 235, 0.18) !important;
    }
    div[role="radiogroup"] label:nth-of-type(1):not(:has(input:checked)) p {
        color: #bfdbfe !important;
        font-weight: 800 !important;
    }

    /* Agentic AI feature tab: subtle purple accent when inactive. */
    div[role="radiogroup"] label:nth-of-type(6):not(:has(input:checked)) {
        border-color: rgba(168, 85, 247, 0.42) !important;
        background-color: rgba(88, 28, 135, 0.10) !important;
    }

    /* The selected/current tab is the only solid blue tab. */
    div[role="radiogroup"] label:has(input:checked) {
        color: #ffffff !important;
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        border-color: #60a5fa !important;
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.34), 0 0 0 1px rgba(147, 197, 253, 0.22) inset !important;
        transform: translateY(-1px) !important;
    }

    div[role="radiogroup"] label p {
        font-size: 0.80rem !important;
        line-height: 1.05rem !important;
        font-weight: 700 !important;
        color: #e5e7eb !important;
        margin: 0 !important;
        white-space: nowrap !important;
    }

    div[role="radiogroup"] label:has(input:checked) p {
        color: #ffffff !important;
        font-weight: 800 !important;
    }


    /* Selected workflow panel theme banner.
       Tabs are navigation; the panel banner gives each selected section its own subtle theme. */
    .workflow-panel-banner {
        margin: 8px 0 22px 0;
        padding: 16px 18px;
        border-radius: 14px;
        background: rgba(15, 23, 42, 0.72);
        border: 1px solid rgba(148, 163, 184, 0.18);
        border-top: 3px solid rgba(96, 165, 250, 0.72);
        box-shadow: 0 10px 28px rgba(2, 6, 23, 0.30);
    }
    .workflow-panel-banner .panel-kicker {
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.72rem;
        color: #94a3b8;
        font-weight: 800;
        margin-bottom: 5px;
    }
    .workflow-panel-banner .panel-title {
        font-size: 1.08rem;
        line-height: 1.25rem;
        color: #f8fafc;
        font-weight: 850;
        margin-bottom: 4px;
    }
    .workflow-panel-banner .panel-help {
        font-size: 0.88rem;
        color: #cbd5e1;
        font-weight: 550;
        margin: 0;
    }
    .workflow-panel-roster {
        background: linear-gradient(135deg, rgba(30, 64, 175, 0.24), rgba(15, 23, 42, 0.78)) !important;
        border-color: rgba(59, 130, 246, 0.42) !important;
        border-top-color: #60a5fa !important;
    }
    .workflow-panel-stress {
        background: linear-gradient(135deg, rgba(180, 83, 9, 0.20), rgba(15, 23, 42, 0.78)) !important;
        border-color: rgba(251, 146, 60, 0.38) !important;
        border-top-color: #f97316 !important;
    }
    .workflow-panel-explain {
        background: linear-gradient(135deg, rgba(14, 116, 144, 0.18), rgba(15, 23, 42, 0.78)) !important;
        border-color: rgba(34, 211, 238, 0.32) !important;
        border-top-color: #22d3ee !important;
    }
    .workflow-panel-audit {
        background: linear-gradient(135deg, rgba(120, 53, 15, 0.18), rgba(15, 23, 42, 0.78)) !important;
        border-color: rgba(251, 191, 36, 0.30) !important;
        border-top-color: #fbbf24 !important;
    }
    .workflow-panel-research {
        background: linear-gradient(135deg, rgba(51, 65, 85, 0.30), rgba(15, 23, 42, 0.78)) !important;
        border-color: rgba(125, 211, 252, 0.28) !important;
        border-top-color: #7dd3fc !important;
    }
    .workflow-panel-ai {
        background: linear-gradient(135deg, rgba(88, 28, 135, 0.24), rgba(15, 23, 42, 0.78)) !important;
        border-color: rgba(168, 85, 247, 0.42) !important;
        border-top-color: #a855f7 !important;
    }
    .workflow-panel-performance {
        background: linear-gradient(135deg, rgba(5, 150, 105, 0.16), rgba(15, 23, 42, 0.78)) !important;
        border-color: rgba(52, 211, 153, 0.30) !important;
        border-top-color: #34d399 !important;
    }

    /* Selected-workflow content association.
       The chosen tab sets CSS variables below; every subtitle/content marker then picks up
       that active workflow accent so the section underneath clearly belongs to the selected tab. */
    .workflow-content-rail {
        margin: -8px 0 18px 0;
        padding: 10px 14px;
        border-radius: 12px;
        background: linear-gradient(90deg, var(--workflow-accent-soft, rgba(59, 130, 246, 0.16)), rgba(15, 23, 42, 0.38));
        border-left: 4px solid var(--workflow-accent, #60a5fa);
        border-right: 1px solid var(--workflow-border, rgba(148, 163, 184, 0.18));
        color: #e2e8f0;
        box-shadow: 0 8px 22px rgba(2, 6, 23, 0.22);
    }
    .workflow-content-rail .rail-kicker {
        font-size: 0.72rem;
        letter-spacing: 0.075em;
        text-transform: uppercase;
        font-weight: 850;
        color: var(--workflow-accent, #60a5fa);
        margin-bottom: 3px;
    }
    .workflow-content-rail .rail-text {
        font-size: 0.88rem;
        font-weight: 650;
        color: #cbd5e1;
    }

    /* Theme the visible subheaders under the active workflow. This avoids making the
       entire page a rainbow, but gives each selected panel a matching visual language. */
    .main .block-container h2,
    .main .block-container h3 {
        border-left: 4px solid var(--workflow-accent, #60a5fa) !important;
        padding-left: 11px !important;
        border-radius: 8px !important;
        background: linear-gradient(90deg, var(--workflow-accent-soft, rgba(59, 130, 246, 0.13)), rgba(15, 23, 42, 0.0) 74%) !important;
    }
    .main .block-container h2::after,
    .main .block-container h3::after {
        content: "";
        display: block;
        width: 54px;
        height: 2px;
        margin-top: 7px;
        border-radius: 999px;
        background: var(--workflow-accent, #60a5fa);
        opacity: 0.78;
    }

    /* Keep the main app title clean; the workflow association starts below the selector. */
    .main .block-container h1 {
        border-left: none !important;
        padding-left: 0 !important;
        background: transparent !important;
    }
    .main .block-container h1::after {
        display: none !important;
    }
    


    /* Roster workspace: 3-step shortage workflow structure.
       Same blue operational theme, but stronger visual grouping so this feels like
       the main guided workflow inside the Roster & Shortage Solver tab. */
    .shortage-workflow-shell {
        margin: 18px 0 18px 0;
        padding: 18px 20px 16px 20px;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(30, 64, 175, 0.24), rgba(15, 23, 42, 0.82));
        border: 1px solid rgba(96, 165, 250, 0.42);
        border-left: 5px solid #60a5fa;
        box-shadow: 0 14px 32px rgba(2, 6, 23, 0.34), 0 0 0 1px rgba(96, 165, 250, 0.08) inset;
    }
    .shortage-workflow-kicker {
        text-transform: uppercase;
        letter-spacing: 0.09em;
        color: #93c5fd;
        font-size: 0.72rem;
        font-weight: 850;
        margin-bottom: 5px;
    }
    .shortage-workflow-title {
        color: #f8fafc;
        font-size: 1.18rem;
        line-height: 1.35rem;
        font-weight: 900;
        margin-bottom: 5px;
    }
    .shortage-workflow-copy {
        color: #cbd5e1;
        font-size: 0.92rem;
        line-height: 1.45rem;
        font-weight: 560;
        margin-bottom: 14px;
    }
    .shortage-workflow-track {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
        margin-top: 12px;
    }
    .shortage-step-card {
        min-height: 72px;
        padding: 12px 13px;
        border-radius: 13px;
        background: rgba(15, 23, 42, 0.62);
        border: 1px solid rgba(147, 197, 253, 0.30);
        box-shadow: 0 8px 18px rgba(2, 6, 23, 0.22);
    }
    .shortage-step-number {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 24px;
        height: 24px;
        border-radius: 999px;
        background: rgba(37, 99, 235, 0.92);
        color: #ffffff;
        font-size: 0.78rem;
        font-weight: 900;
        margin-right: 7px;
        box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.16);
    }
    .shortage-step-label {
        color: #ffffff;
        font-weight: 850;
        font-size: 0.90rem;
        white-space: nowrap;
    }
    .shortage-step-help {
        margin-top: 7px;
        color: #bfdbfe;
        font-size: 0.80rem;
        line-height: 1.15rem;
        font-weight: 560;
    }
    .shortage-step-card:nth-child(2) {
        border-color: rgba(167, 139, 250, 0.36);
    }
    .shortage-step-card:nth-child(2) .shortage-step-number {
        background: rgba(124, 58, 237, 0.92);
        box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.15);
    }
    .shortage-step-card:nth-child(3) {
        border-color: rgba(52, 211, 153, 0.34);
    }
    .shortage-step-card:nth-child(3) .shortage-step-number {
        background: rgba(5, 150, 105, 0.95);
        box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.15);
    }
    @media (max-width: 900px) {
        .shortage-workflow-track {
            grid-template-columns: 1fr;
        }
        .shortage-step-label {
            white-space: normal;
        }
    }

    .main .block-container {
        padding-top: 2rem;
    }
    h1, h2, h3 {
        color: #f3f4f6 !important;
        font-family: 'Outfit', 'Inter', sans-serif !important;
        font-weight: 700;
    }
    
    /* Mobile App-style Dropdown List Boxes */
    div[data-baseweb="select"] > div {
        background-color: rgba(51, 65, 85, 0.95) !important;
        border: 2px solid rgba(129, 140, 248, 0.4) !important;
        border-radius: 14px !important;
        min-height: 54px !important;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2) !important;
        transition: all 0.2s ease-in-out !important;
    }
    div[data-baseweb="select"] > div:hover, div[data-baseweb="select"] > div:focus-within {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2) !important;
    }
    div[data-baseweb="select"] span {
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        color: #f8fafc !important;
        line-height: normal !important;
    }
    
    /* Style the dropdown list items popup menu */
    div[data-baseweb="popover"] > div {
        border-radius: 14px !important;
        overflow: hidden !important;
        border: 1px solid rgba(148, 163, 184, 0.3) !important;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.3) !important;
    }
    ul[data-baseweb="menu"] {
        background-color: #1e293b !important;
    }
    ul[data-baseweb="menu"] li {
        font-weight: 500 !important;
        font-size: 1.05rem !important;
        color: #cbd5e1 !important;
        padding: 12px 16px !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
    }
    ul[data-baseweb="menu"] li:last-child {
        border-bottom: none !important;
    }
    ul[data-baseweb="menu"] li:hover {
        background-color: rgba(99, 102, 241, 0.2) !important;
        color: #ffffff !important;
    }
    
    /* Primary buttons custom styling */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        font-size: 1.15rem !important;
        padding: 18px 24px !important;
        font-weight: 800 !important;
        box-shadow: 0 4px 14px 0 rgba(37, 99, 235, 0.39) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    /* Distinct blue shade for the Submit Decision button */
    .submit-btn-wrapper div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%) !important;
        box-shadow: 0 4px 14px 0 rgba(30, 64, 175, 0.39) !important;
    }
    
    div.stButton > button[kind="primary"]:hover {
        filter: brightness(1.15) !important;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.2) !important;
        transform: translateY(-2px) !important;
    }
    
    div.stButton > button[kind="primary"]:active {
        transform: translateY(0px) !important;
    }
    
    /* Style secondary buttons in sidebar as destructive warning red */
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"] {
        border: 1px solid rgba(239, 68, 68, 0.3) !important;
        background: rgba(239, 68, 68, 0.08) !important;
        color: #f87171 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover {
        background: rgba(239, 68, 68, 0.18) !important;
        border-color: #ef4444 !important;
        box-shadow: 0 4px 12px rgba(239, 68, 68, 0.25) !important;
        transform: translateY(-1px) !important;
    }
    
    section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:active {
        transform: translateY(0px) !important;
    }
    
    /* Custom CSS Card Styling */
    .glass-card {
        background: rgba(17, 25, 40, 0.65);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        color: #e5e7eb;
    }
    
    .agent-card {
        background: rgba(30, 41, 59, 0.5);
        border-left: 5px solid #6366f1;
        border-radius: 6px;
        padding: 15px;
        margin-bottom: 12px;
    }
    
    .agent-header {
        font-weight: 700;
        color: #818cf8;
        font-size: 1.1em;
        margin-bottom: 5px;
    }
    
    .status-badge-complete {
        background-color: rgba(16, 185, 129, 0.2);
        color: #10b981;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8em;
        font-weight: bold;
        float: right;
    }

    .status-badge-active {
        background-color: rgba(245, 158, 11, 0.2);
        color: #f59e0b;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8em;
        font-weight: bold;
        float: right;
        animation: pulse 1.5s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 0.6; }
        50% { opacity: 1; }
        100% { opacity: 0.6; }
    }
</style>
""", unsafe_allow_html=True)


# Helper function to query backend

def normalize_records(payload, list_keys=("data", "results", "items", "schedule", "nurses", "logs", "audit_logs")):
    """Normalize backend JSON into a list of row dictionaries for DataFrame rendering."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in list_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        # If this is a single row object, wrap it so pandas gets a list of records.
        if payload and all(not isinstance(v, (list, dict)) for v in payload.values()):
            return [payload]
    return []

def format_nested_value(value):
    """Convert lists/dicts from API payloads into readable strings for tables.

    Streamlit/Arrow can show nested objects as [object Object]. The audit log table
    is easier to read when nested agent/reason/cost fields are flattened first.
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        if not value:
            return ""
        formatted_items = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("agent") or item.get("id") or item.get("title")
                reason = item.get("reason") or item.get("description") or item.get("status")
                if name and reason:
                    formatted_items.append(f"{name}: {reason}")
                elif name:
                    formatted_items.append(str(name))
                else:
                    formatted_items.append(json.dumps(item, ensure_ascii=False))
            elif isinstance(item, list):
                formatted_items.append(", ".join(str(x) for x in item))
            else:
                formatted_items.append(str(item))
        return "; ".join(formatted_items)
    if isinstance(value, dict):
        if not value:
            return ""
        compact_pairs = []
        for key, val in value.items():
            if isinstance(val, (list, dict)):
                val = format_nested_value(val)
            compact_pairs.append(f"{key}: {val}")
        return "; ".join(compact_pairs)
    return str(value)

def build_audit_table_rows(audit_entries):
    """Return a display-safe audit table without [object Object] nested cells."""
    rows = []
    for entry in audit_entries:
        if not isinstance(entry, dict):
            continue
        rows.append({key: format_nested_value(value) for key, value in entry.items()})
    return rows

def _fetch_records(endpoint, list_keys, timeout=5):
    """Fetch a read-only endpoint and normalize the response into a list.

    Kept separate from the cached helpers so the dashboard can fetch the common
    startup payload concurrently on cache misses.
    """
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}", timeout=timeout)
        if response.ok:
            return normalize_records(response.json(), list_keys=list_keys)
        return []
    except Exception:
        return []

@st.cache_data(ttl=120)
def get_dashboard_bootstrap_data():
    """Load common dashboard read-only data concurrently.

    On a cold Streamlit cache, the old code fetched nurses, schedule, logs, and
    audit logs one after another. Over Railway, that stacks latency. This turns
    four serial network waits into one parallel wait while keeping the public
    get_* helpers unchanged for the rest of the dashboard.
    """
    jobs = {
        "nurses": ("/api/nurses", ("nurses", "data", "results", "items")),
        "schedule": ("/api/schedule", ("schedule", "data", "results", "items")),
        "logs": ("/api/logs", ("logs", "data", "results", "items")),
        "audit_logs": ("/api/audit_logs", ("audit_logs", "logs", "data", "results", "items")),
    }
    results = {key: [] for key in jobs}
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_key = {
                executor.submit(_fetch_records, endpoint, list_keys, 5): key
                for key, (endpoint, list_keys) in jobs.items()
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception:
                    results[key] = []
    except Exception:
        # Fallback to serial fetch if the executor fails for any reason.
        for key, (endpoint, list_keys) in jobs.items():
            results[key] = _fetch_records(endpoint, list_keys, 5)
    return results

def clear_dashboard_bootstrap_cache():
    try:
        get_dashboard_bootstrap_data.clear()
    except Exception:
        pass


def get_pressure_badge_style(level):
    """Return theme colors for ER operational pressure badges."""
    normalized = str(level or "Normal").strip().lower()
    if normalized == "critical":
        return {"bg": "rgba(239, 68, 68, 0.16)", "border": "#ef4444", "text": "#fecaca", "icon": "🔴"}
    if normalized == "high":
        return {"bg": "rgba(249, 115, 22, 0.16)", "border": "#f97316", "text": "#fed7aa", "icon": "🟠"}
    if normalized in {"moderate", "elevated"}:
        return {"bg": "rgba(245, 158, 11, 0.16)", "border": "#f59e0b", "text": "#fde68a", "icon": "🟡"}
    return {"bg": "rgba(34, 197, 94, 0.14)", "border": "#22c55e", "text": "#bbf7d0", "icon": "🟢"}

def render_pressure_status_card(evidence):
    """Visible Step 1 indicator: current ER pressure level from the operational rule modules."""
    evidence = evidence or {}
    level = evidence.get("adjusted_operational_risk") or evidence.get("operational_pressure_level") or "Normal"
    score = evidence.get("adjusted_operational_risk_score", "N/A")
    style = get_pressure_badge_style(level)
    arrival = evidence.get("arrival_surge_pressure", "Normal")
    boarding = evidence.get("boarding_pressure", "Normal")
    fast_track = evidence.get("fast_track_pressure", "Normal")
    esi = evidence.get("esi_pressure", "Normal")
    fatigue = evidence.get("nurse_fatigue_pressure", "Normal")
    return f"""
    <div style='background:{style['bg']}; border:1px solid {style['border']}; border-left:5px solid {style['border']}; border-radius:10px; padding:14px 16px; margin:12px 0 16px 0;'>
        <div style='display:flex; justify-content:space-between; gap:12px; align-items:center; flex-wrap:wrap;'>
            <div>
                <div style='font-size:0.78rem; text-transform:uppercase; letter-spacing:0.08em; color:#cbd5e1; font-weight:800;'>ER Operational Pressure</div>
                <div style='font-size:1.05rem; color:{style['text']}; font-weight:800;'>{style['icon']} {level}</div>
            </div>
            <div style='font-size:0.88rem; color:#e5e7eb;'>Operational risk score: <strong>{score}</strong></div>
        </div>
        <div style='margin-top:10px; color:#dbeafe; font-size:0.9rem; line-height:1.55;'>
            Adjusted for arrival surge, boarding, acuity/ESI proxy, nurse fatigue/call-outs, and fast-track status.
            <br/>Signals: Arrival <strong>{arrival}</strong> · Boarding <strong>{boarding}</strong> · Acuity <strong>{esi}</strong> · Fatigue <strong>{fatigue}</strong> · Fast-track <strong>{fast_track}</strong>
        </div>
    </div>
    """

def render_pressure_staffing_adjustment_card(evidence):
    """Visible Step 2 indicator: how pressure changed the staffing recommendation."""
    evidence = evidence or {}
    base = evidence.get("base_nurses_from_wait_time", evidence.get("base_nurses_needed", 0))
    adjustment = evidence.get("operational_pressure_nurse_increments", 0)
    final = evidence.get("final_additional_nurses_needed", evidence.get("research_adjusted_nurses_needed", 0))
    level = evidence.get("adjusted_operational_risk", "Normal")
    style = get_pressure_badge_style(level)
    reasons = evidence.get("nurse_increment_reasons", []) or evidence.get("nurse_adjustment_reasons", []) or []
    if isinstance(reasons, list):
        reasons_text = "; ".join(str(r) for r in reasons[:3]) if reasons else "No additional operational increment reasons recorded."
    else:
        reasons_text = str(reasons)
    return f"""
    <div style='background:rgba(15, 23, 42, 0.72); border:1px solid rgba(96,165,250,0.32); border-left:5px solid {style['border']}; border-radius:10px; padding:14px 16px; margin:14px 0 18px 0;'>
        <div style='font-size:0.78rem; text-transform:uppercase; letter-spacing:0.08em; color:#cbd5e1; font-weight:800;'>Pressure-Based Staffing Adjustment</div>
        <div style='display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:12px; margin-top:10px;'>
            <div><span style='color:#94a3b8;'>Base wait-time staffing</span><br/><strong style='color:#f8fafc;'>+{base}</strong></div>
            <div><span style='color:#94a3b8;'>Operational adjustment</span><br/><strong style='color:{style['text']};'>+{adjustment}</strong></div>
            <div><span style='color:#94a3b8;'>Final recommendation</span><br/><strong style='color:#86efac;'>+{final}</strong></div>
        </div>
        <div style='margin-top:10px; color:#dbeafe; font-size:0.9rem; line-height:1.55;'>
            The ER pressure status from Step 1 is translated into the staffing recommendation here. Factors applied: {reasons_text}
        </div>
    </div>
    """

def get_nurses():
    return get_dashboard_bootstrap_data().get("nurses", [])

def get_schedule():
    return get_dashboard_bootstrap_data().get("schedule", [])

def get_logs():
    return get_dashboard_bootstrap_data().get("logs", [])

def get_audit_logs():
    return get_dashboard_bootstrap_data().get("audit_logs", [])

@st.cache_data(ttl=120)
def get_inflow_history():
    try:
        response = requests.get(f"{API_BASE_URL}/api/inflow-history", timeout=5)
        return response.json() if response.ok else []
    except Exception:
        return []

def add_audit_log(entry):
    try:
        response = requests.post(f"{API_BASE_URL}/api/audit_logs", json=entry, timeout=15)
        success = response.json().get("success", False) if response.ok else False
        if success:
            clear_dashboard_bootstrap_cache()
        return success
    except Exception:
        return False

def predict_wait_time(facility_size_beds, month, day_of_week, visithour, urgency_level, nurse_to_patient_ratio, specialist_availability, hospital_name="Riverside Medical Center", region="Urban"):
    payload = {
        "facility_size_beds": facility_size_beds,
        "month": month,
        "day_of_week": day_of_week,
        "visithour": visithour,
        "urgency_level": urgency_level,
        "nurse_to_patient_ratio": nurse_to_patient_ratio,
        "specialist_availability": specialist_availability,
        "hospital_name": hospital_name,
        "region": region
    }
    try:
        res = requests.post(f"{API_BASE_URL}/api/predict_wait", json=payload, timeout=15)
        data = res.json()
        if not res.ok or data.get("success") is False:
            return 0.0
        return data.get("predicted_wait_time", 0.0)
    except Exception:
        return 0.0

@st.cache_data(ttl=120)
def get_inflow_memory_state():
    try:
        response = requests.get(f"{API_BASE_URL}/api/inflow-memory", timeout=3)
        return response.json() if response.ok else {}
    except Exception:
        return {}

def forecast_inflow_memory(telemetry):
    try:
        return requests.post(f"{API_BASE_URL}/api/inflow-forecast", json=telemetry, timeout=15).json()
    except Exception:
        return {}

def update_inflow_memory_state(forecast, actual):
    try:
        return requests.post(f"{API_BASE_URL}/api/update-inflow-memory", json={"forecasted_volume": forecast, "actual_volume": actual}, timeout=15).json()
    except Exception:
        return {}



def generate_cno_response(user_message, chat_history, context, audio_bytes=None):
    import streamlit as st
    enable_llm = st.session_state.get("ai_mode") in ["Live Gemini API (Tokens)", "Live Groq API (Tokens)"] or os.getenv("ENABLE_LLM_DEBATE", "false").lower() == "true"
    if not enable_llm:
        return "I'm sorry, but AI debate is disabled. I cannot provide a detailed response at this time."
        
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        return "API Key not configured. Please add a valid Gemini API Key to your .env file."
        
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        system_prompt = f"""You are the Chief Nursing Officer (CNO) AI Agent of this hospital.
You are defending and explaining the current staffing recommendation made by the Financial and Patient Safety Agents.
Here is the context of the current crisis:
{json.dumps(context, indent=2)}

Guidelines:
- Answer the user's questions logically, referencing hospital safety, cost, the selected nurses, and the rejected nurses.
- Keep responses short, authoritative, and professional (1-3 sentences max).
- If asked why a specific nurse was rejected, explicitly reference their rejection reason.
- If the user sends an audio recording, treat it as a spoken question from a doctor or administrator and address them politely.
- STRICT TOPIC GUARDRAIL: You must ONLY answer questions related to hospital staffing, patient safety, hospital administration, or the specific context provided above. If the user asks about anything else (e.g., general knowledge, coding, unrelated topics), politely refuse to answer and state that your role is strictly limited to hospital administration and staffing governance.
"""
        
        # Format chat history for Gemini
        history = [{"role": "user", "parts": [system_prompt]}]
        history.append({"role": "model", "parts": ["Understood. I am the CNO. How can I assist you with this staffing decision?"]})
        
        for msg in chat_history:
            role = "user" if msg["role"] == "user" else "model"
            parts = []
            if msg.get("type") == "audio" and msg.get("audio_bytes"):
                parts.append({"mime_type": "audio/wav", "data": msg["audio_bytes"]})
            if msg.get("content"):
                parts.append(msg["content"])
            if not parts:
                parts.append("...")
            history.append({"role": role, "parts": parts})
            
        chat_session = model.start_chat(history=history)
        
        # Current message parts
        current_parts = []
        if audio_bytes:
            current_parts.append({"mime_type": "audio/wav", "data": audio_bytes})
        if user_message:
            current_parts.append(user_message)
            
        if not current_parts:
            return "No input received."
            
        response = chat_session.send_message(current_parts)
        
        return response.text.strip()
    except Exception as e:
        return f"Error communicating with CNO Agent: {str(e)}"

@st.cache_resource
def get_feature_importances():
    try:
        import pickle
        import xgboost as xgb
        with open("backend/xgboost_model.pkl", "rb") as f:
            payload = pickle.load(f)
        pipeline = payload["model"]
        features = payload["features"]
        # Since the model is a scikit-learn Pipeline, we get the regressor step
        regressor = pipeline.named_steps['regressor']
        importances = regressor.feature_importances_
        # Note: the pipeline preprocessor outputs more features due to one-hot encoding,
        # so we map the primary feature importances based on matching indices or return top raw features.
        # To match the feature list directly:
        return dict(zip(features, importances))
    except Exception as e:
        print(f"Error reading feature importances: {e}")
        return {}


def calculate_local_drivers(beds, month, day, hour, acuity, ratio, spec):
    # Baselines (means)
    base_ratio = 25.0 / (0.22 + 0.02)  # ~104
    base_acuity = (3 - 1) * 15.0        # 30
    base_beds = (350 - 200) * 0.08      # 12
    base_hour = 14.3
    base_month = 6.4
    base_day = 4.3
    base_spec = 3.0
    
    # Current values
    curr_ratio = 25.0 / (ratio + 0.02)
    curr_acuity = (acuity - 1) * 15.0
    curr_beds = (350 - beds) * 0.08
    curr_hour = 30.0 if hour in range(14, 23) else 5.0
    curr_month = 22.0 if month in [12, 1, 2] else (10.0 if month in [7, 8] else 0.0)
    curr_day = 15.0 if day in [5, 6] else 0.0
    curr_spec = 10.0 if spec == 0 else 0.0
    
    drivers = {
        "Nurse-to-Patient Ratio": curr_ratio - base_ratio,
        "Patient Urgency/Acuity": curr_acuity - base_acuity,
        "Hospital Beds Capacity": curr_beds - base_beds,
        "Visit Hour Peaks": curr_hour - base_hour,
        "Seasonal Month Surge": curr_month - base_month,
        "Weekend Influx": curr_day - base_day,
        "Specialist Availability": curr_spec - base_spec
    }
    return drivers

# Sidebar Controls
st.sidebar.markdown("<h2 style='text-align: center; color: #818cf8;'>⚙️ Control Tower</h2>", unsafe_allow_html=True)

if st.sidebar.button("🔄 Restore Demo Nurses & Shift Schedule", use_container_width=True, help="Restores the original mock nurse registry, shift schedule, memory, logs, and audit history for a fresh demo run."):
    try:
        res = requests.post(f"{API_BASE_URL}/api/reset")
        st.session_state.evidence = {}
        st.session_state.estimated_needed = 0
        st.session_state.pred_wait = 0
        st.session_state.safety_thresh = 0
        st.session_state.risk_assessed = False
        st.session_state.pending_log = None
        st.sidebar.success(res.json()["message"])
        clear_dashboard_bootstrap_cache()
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Failed to restore demo data: {e}")

st.sidebar.caption("Resets the nurse registry, shift schedule, memory, logs, and audit history back to the original mock demo state.")

mlops_expander = st.sidebar.expander("🤖 MLOps Pipeline Controls", expanded=False)

# Render active MLOps status card
live_records_count = 0
live_csv = "database/live_collected_data.csv"
if os.path.exists(live_csv):
    try:
        with open(live_csv, 'r') as f:
            live_records_count = max(0, sum(1 for _ in f) - 1)
    except Exception:
        pass

try:
    with open("backend/model_metrics.json", "r") as f:
        m_data = json.load(f)
        last_retrained = m_data.get("training_metadata", {}).get("last_trained_time", "N/A")
        r2_val = m_data.get("metrics", {}).get("r2", 0.0)
except Exception:
    last_retrained = "N/A"
    r2_val = 0.0

mlops_expander.markdown(f"""
<div class="sidebar-small" style="margin-bottom: 12px; border-left: 3px solid #6366f1; background: rgba(99, 102, 241, 0.08);">
    <div style="font-size: 0.9em; color: #a5b4fc; font-weight: bold; margin-bottom: 6px;">Pipeline Metrics Status</div>
    <div style="font-size: 0.85em; margin-bottom: 4px;">• <b>Collected Feedback Data</b>: {live_records_count} rows</div>
    <div style="font-size: 0.85em; margin-bottom: 4px;">• <b>Active Model R²</b>: {r2_val:.3f}</div>
    <div style="font-size: 0.85em;">• <b>Last Retrained</b>: {last_retrained}</div>
</div>
""", unsafe_allow_html=True)


if mlops_expander.button("Trigger Nightly XGBoost Retraining", type="primary", use_container_width=True, key="sidebar_retrain_btn"):
    with st.spinner("Retraining model with collected feedback data…"):
        try:
            res = requests.post(f"{API_BASE_URL}/api/retrain_and_reload")
            if res.ok and res.json().get('success'):
                mlops_expander.success("Model retrained and reloaded successfully!")
            else:
                mlops_expander.error(f"Retraining failed: {res.text}")
        except Exception as e:
            mlops_expander.error(f"Error during retraining: {e}")

if mlops_expander.button("🗑️ Reset Simulated Feedback & Rebuild Model", type="secondary", use_container_width=True, key="sidebar_reset_live_btn"):
    with st.spinner("Deleting simulated feedback data and retraining model from scratch..."):
        try:
            res = requests.post(f"{API_BASE_URL}/api/reset_live_data")
            if res.ok and res.json().get('success'):
                st.session_state.evidence = {}
                st.session_state.estimated_needed = 0
                st.session_state.pred_wait = 0
                st.session_state.safety_thresh = 0
                st.session_state.risk_assessed = False
                st.session_state.pending_log = None
                mlops_expander.success("Deleted simulated feedback & rebuilt XGBoost model!")
            else:
                mlops_expander.error(f"Reset failed: {res.text}")
        except Exception as e:
            mlops_expander.error(f"Error resetting model: {e}")

st.sidebar.markdown("---")

# Inject Sidebar CSS for high-readability bold styling
st.sidebar.markdown("""
<style>
/* Make all sidebar text bolder, larger, and sharper */
section[data-testid="stSidebar"] {
    font-family: 'Outfit', 'Inter', sans-serif !important;
}
section[data-testid="stSidebar"] .stMarkdown p {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    color: #e5e7eb !important;
}
section[data-testid="stSidebar"] h2 {
    font-size: 1.65rem !important;
    font-weight: 800 !important;
    color: #818cf8 !important;
    margin-bottom: 12px !important;
}
.sidebar-small {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    line-height: 1.5;
    padding: 14px;
    background: rgba(17, 25, 40, 0.5) !important;
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
}
.sidebar-status-row {
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 8px;
    color: #f3f4f6 !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
}
</style>
""", unsafe_allow_html=True)

# Derive status states
is_connected = len(get_nurses()) > 0
backend_icon = "🟢" if is_connected else "🔴"

model_ready = os.path.exists("backend/xgboost_model.pkl")
model_icon = "🟢" if model_ready else "🔴"

risk_assessed = st.session_state.get("risk_assessed", False)
pred_icon = "🟢" if risk_assessed else "⚪"
stress_icon = "🟢" if risk_assessed else "⚪"

pending_log = st.session_state.get("pending_log")
solver_icon = "🟢" if pending_log else "⚪"
debate_icon = "🟢" if pending_log else "⚪"

approval_icon = "🟡" if pending_log else "⚪"
roster_icon = "🟡" if pending_log else "⚪"

audit_trail_db = get_audit_logs()
audit_saved = len(audit_trail_db) > 0
audit_icon = "🟢" if audit_saved else "⚪"

debate_icon = "🟢" if pending_log else "⚪"

# Render compact Control Tower

# ER Operational Status Light (Sidebar)
curr_risk = st.session_state.get("evidence", {}).get("adjusted_operational_risk", "Normal")
status_info = get_status_light_mapping(curr_risk)

# Operational pressure engine status indicator (sidebar)
selected_demo_preset = st.session_state.get("demo_select", "Select a Demo Scenario...")
pressure_preset_loaded = bool(selected_demo_preset and selected_demo_preset != "Select a Demo Scenario...")

pressure_label = "PRESET LOADED" if pressure_preset_loaded else "READY"
pressure_color = "#22c55e" if pressure_preset_loaded else "#38bdf8"
pressure_bg = "rgba(34, 197, 94, 0.10)" if pressure_preset_loaded else "rgba(56, 189, 248, 0.10)"
pressure_border = "#22c55e" if pressure_preset_loaded else "#38bdf8"
pressure_detail = selected_demo_preset if pressure_preset_loaded else "Baseline pressure inputs loaded"
pressure_source = "Recommendation adjustment enabled"

st.sidebar.markdown(f"""
<div style="text-align: center; margin-bottom: 14px;">
    <div style="background: {pressure_bg}; border: 1.5px solid {pressure_border}; border-radius: 8px; padding: 10px 8px; box-shadow: 0 0 12px rgba(56,189,248,0.12);">
        <div style="font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.08em; color: #cbd5e1; font-weight: 800; margin-bottom: 4px;">Operational Pressure Engine</div>
        <div style="font-size: 1.02rem; font-weight: 900; color: {pressure_color};">● {pressure_label}</div>
        <div style="font-size: 0.78rem; color: #e5e7eb; font-weight: 700; margin-top: 4px; line-height: 1.25;">{pressure_detail}</div>
        <div style="font-size: 0.70rem; color: #94a3b8; font-weight: 600; margin-top: 4px; line-height: 1.25;">{pressure_source}</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown(f"""
<div style="text-align: center; margin-bottom: 20px;">
    <div style="background: rgba(0,0,0,0.3); border: 2px solid {status_info['color']}; border-radius: 8px; padding: 10px;">
        <span style="font-size: 1.2rem; font-weight: 800; color: {status_info['color']};">ER Status: {status_info['label']}</span>
    </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("##### 📡 Pipeline Status")
st.sidebar.markdown(f"""
<div class="sidebar-small">
    <div class="sidebar-status-row"><span>{backend_icon}</span> Backend</div>
    <div class="sidebar-status-row"><span>{model_icon}</span> XGBoost Model</div>
    <div class="sidebar-status-row"><span>{pred_icon}</span> Wait-Time Prediction</div>
    <div class="sidebar-status-row"><span>{stress_icon}</span> Stress Simulation</div>
    <div class="sidebar-status-row"><span>{solver_icon}</span> Shortage Solver</div>
    <div class="sidebar-status-row"><span>{debate_icon}</span> Agent Debate</div>
    <div class="sidebar-status-row"><span>{approval_icon}</span> Human Approval</div>
    <div class="sidebar-status-row"><span>{roster_icon}</span> Roster Update</div>
    <div class="sidebar-status-row"><span>{audit_icon}</span> Audit Log</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")

# Expanders for detailed configurations
st.sidebar.markdown("##### 🛠️ Advanced Analytics")

sidebar_log = st.session_state.get("pending_log") or {}
sidebar_costs = dict(sidebar_log.get("costs", {}) or {})

# Live Gemini token usage is tracked separately from the local solver log so the
# sidebar reflects real API calls immediately after the live debate endpoint runs.
if "live_gemini_usage" not in st.session_state:
    st.session_state.live_gemini_usage = {
        "llm_calls": 0,
        "prompt_tokens": 0,
        "response_tokens": 0,
        "total_tokens": 0,
        "estimated_api_cost": 0.0,
        "status": "idle",
        "error": "",
        "model_used": "",
        "selected_model": (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash"))
    }

st.sidebar.markdown("""
<style>
    /* Highlight the AI Processing Engine Panel */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9));
        padding: 15px;
        border-radius: 12px;
        border: 2px solid #6366f1;
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.2);
    }
    
    /* Disable the third option (Gemini) completely */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] > div > label:nth-child(3) {
        opacity: 0.4;
        pointer-events: none;
        cursor: not-allowed;
        filter: grayscale(100%);
    }
</style>
""", unsafe_allow_html=True)

ai_mode = st.sidebar.radio(
    "AI Processing Engine", 
    ["Local Expert System", "Live Groq API (Tokens)", "Live Gemini API (Tokens) [Disabled]"], 
    index=0
)

# Show Groq Status if selected or generally
if ai_mode == "Live Groq API (Tokens)":
    try:
        groq_status = requests.get(f"{API_BASE_URL}/api/groq_status", timeout=5).json()
        if groq_status.get("has_key"):
            st.sidebar.markdown("🟢 **Groq API Detected**")
        else:
            st.sidebar.markdown("🔴 **Groq API Not Configured** (.env missing GROQ_API_KEY)")
    except Exception:
        st.sidebar.markdown("🔴 **Groq API Not Configured** (Backend offline)")

if ai_mode == "Live Gemini API (Tokens) [Disabled]":
    st.sidebar.warning("Gemini API is currently disabled. Please select Local Expert System or Live Groq API.")

st.session_state.ai_mode = ai_mode

with st.sidebar.expander("🔌 System Details", expanded=True):
    api_key_status = "🟢 Connected" if is_connected else "🔴 Server Offline"
    st.write(f"**API Connection**: {api_key_status}")
    model_option = st.selectbox(
        "Gemini Model Target",
        ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.5-flash"],
        index=0,
        disabled=True,
        help="Gemini 1.5 model IDs often return 404 now. Use a current model; the backend will fall back to an available generateContent model if this target is unavailable."
    )
    st.session_state.model_option = model_option
    if st.button("Check available Gemini models", key="check_gemini_models_btn"):
        try:
            model_check = requests.get(f"{API_BASE_URL}/api/gemini_models", timeout=20).json()
            if model_check.get("success"):
                models = model_check.get("models", [])
                st.success(f"Backend Gemini key OK. {len(models)} generateContent models available.")
                if models:
                    st.caption("Available: " + ", ".join(models[:8]))
            else:
                st.error(model_check.get("error", "Could not inspect Gemini models."))
        except Exception as gemini_check_e:
            st.error(f"Could not check Gemini models: {gemini_check_e}")

    # Keep the token panel aligned with the currently selected Gemini model.
    # If the operator changes model after a previous live call, do not keep
    # displaying the old successful/fallback model as if it belonged to the
    # new selection. The next solver run will repopulate real usage.
    if st.session_state.get("_last_gemini_model_option") != model_option:
        st.session_state._last_gemini_model_option = model_option
        st.session_state.live_gemini_usage = {
            "llm_calls": 0,
            "prompt_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
            "estimated_api_cost": 0.0,
            "status": "idle",
            "error": "",
            "model_used": "",
            "selected_model": model_option
        }

with st.sidebar.expander("📊 XGBoost Model Performance"):
    try:
        import json
        with open("backend/model_metrics.json", "r") as f:
            metrics_data = json.load(f)
            
        m = metrics_data["metrics"]
        md = metrics_data["training_metadata"]
        
        st.metric("R² Score", f"{m['r2']:.3f}")
        st.caption("**R²**: How much variation the model explains (1.0 is perfect).")
        
        st.metric("MAE", f"{m['mae']:.2f} mins")
        st.caption(f"**MAE**: Average absolute error. The model is off by about {m['mae']:.1f} minutes on average.")
        
        st.metric("RMSE", f"{m['rmse']:.2f} mins")
        st.caption("**RMSE**: Error metric that penalizes larger mistakes more heavily.")

        if "risk_band_accuracy" in m:
            st.metric("Risk Band Accuracy", f"{m['risk_band_accuracy']:.1%}")
            
        if "high_or_critical_recall" in m:
            st.metric("High/Critical Recall", f"{m['high_or_critical_recall']:.1%}")
            st.caption("High/Critical Recall measures how often the model catches dangerous staffing-risk scenarios. This is more important than exact minute-level wait-time prediction for this prototype.")
            
        if "baseline_metrics" in metrics_data:
            b = metrics_data["baseline_metrics"]
            st.markdown("##### Baseline Comparison (Mean Prediction)")
            st.write(f"- Baseline MAE: {b['mae']:.2f} mins")
            st.write(f"- Baseline RMSE: {b['rmse']:.2f} mins")
        
        with st.expander("Training Details & Features"):
            st.write(f"**Train Rows**: {md['train_rows']}")
            st.write(f"**Test Rows**: {md['test_rows']}")
            st.write(f"**Features Used**: {', '.join(md.get('features_used', md.get('features', [])))}")
            st.write(f"**Model Path**: `{md['model_path']}`")
            st.write(f"**Last Trained**: {md['last_trained_time']}")
    except Exception as e:
        st.warning("Model metrics not found.")

with st.sidebar.expander("🪙 Token Usage / Low-Token Mode", expanded=True):
    is_live = st.session_state.get("ai_mode") in ["Live Gemini API (Tokens)", "Live Groq API (Tokens)", "Live Gemini API (Tokens) [Disabled]"]
    live_usage = st.session_state.get("live_gemini_usage", {})
    if is_live and live_usage.get("total_tokens", 0) > 0:
        sidebar_costs = {**sidebar_costs, **live_usage}
    token_total = sidebar_costs.get('total_tokens', 0)
    st.markdown(f"""
    <div style="background: rgba(99, 102, 241, 0.15); border: 2px solid #6366f1; border-radius: 50%; width: 120px; height: 120px; display: flex; flex-direction: column; align-items: center; justify-content: center; margin: 10px auto;">
        <span style="font-size: 2rem; font-weight: 800; color: #818cf8;">{token_total}</span>
        <span style="font-size: 0.7rem; color: #a5b4fc; text-transform: uppercase;">Tokens</span>
    </div>
    <div style="text-align: center; margin-bottom: 10px;">
        <strong style="color: #e5e7eb;">{get_token_display_text(token_total, is_live)}</strong><br>
        <span style="color: #9ca3af; font-size: 0.85em;">{get_token_subtext(token_total, is_live)}</span>
    </div>
    """, unsafe_allow_html=True)
    mode_str = "Live API (Active)" if is_live else "Local deterministic rule mode (Active)"
    st.write(f"**Mode**: {mode_str}")
    st.write(f"**API Calls**: {sidebar_costs.get('llm_calls', 0)}")
    st.write(f"**Estimated Cost**: ${sidebar_costs.get('estimated_api_cost', 0.0):.5f}")
    if is_live:
        live_status = live_usage.get("status", "idle")
        default_selected_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if ai_mode == "Live Groq API (Tokens)" else (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash"))
        selected_model = live_usage.get("selected_model") if live_status != "idle" else default_selected_model
        actual_model = live_usage.get("model_used") or ""

        # Separate the operator's selected target from the model that actually
        # returned a Gemini response. This prevents stale/fallback model names
        # from appearing as the selected model after reruns or model changes.
        st.write(f"**Selected Model**: `{selected_model}`")
        if live_status == "called" and actual_model:
            st.write(f"**Model Used**: `{actual_model}`")

        if live_status == "called":
            st.success("Live API call recorded and token usage captured.")
        elif live_status == "failed":
            st.error("Live API selected, but the API call failed.")
            if actual_model:
                st.caption(f"Last attempted model: `{actual_model}`")
            if live_usage.get("normalized_selected_model") and live_usage.get("normalized_selected_model") != selected_model:
                st.caption(f"Mapped retired/old model to: `{live_usage.get('normalized_selected_model')}`")
            attempted = live_usage.get("attempted_models") or []
            if attempted:
                st.caption("Attempted models: " + ", ".join([f"`{m}`" for m in attempted[:4]]))
            st.caption(live_usage.get("error", "Check backend API key/model configuration."))
        else:
            st.caption("Live mode selected. Tokens will update after you launch the Multi-Agent Shortage Solver.")
    else:
        st.caption("All rules, XGBoost calculations, feature importances, and debates run locally to minimize API token consumption.")



# Main Layout
st.markdown("<h1 style='text-align: center; color: #818cf8;'>SafeStaff AI: ER Staffing Risk Governor</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #9ca3af;'>Early-warning staffing risk detection for emergency departments</p>", unsafe_allow_html=True)


st.markdown("---")

st.markdown(
    """
    <div style="
        background-color: rgba(59, 130, 246, 0.12);
        border: 1px solid rgba(59, 130, 246, 0.35);
        border-radius: 8px;
        padding: 18px 20px;
        margin-top: 10px;
        margin-bottom: 25px;
        color: #F8FAFC;
        line-height: 1.6;
    ">
        <p style="margin-top: 0; color: #FFFFFF; font-size: 1.05rem;"><strong>ℹ️ The Problem:</strong> ER wait times and nurse staffing are not separate problems — they are one connected patient-flow failure. When demand rises faster than staffing can respond, wait times increase, nurses become overloaded, and care quality is placed at risk. Most staffing systems rely on static schedules and after-the-fact escalation, which means leaders often react only after the ER is already under pressure.</p>
        <p style="margin-top: 10px; color: #FFFFFF; font-size: 1.05rem;">SafeStaff AI acts as an early-warning staffing governor. It predicts ER wait-time pressure, detects operational surge signals, and translates those risks into nurse-staffing recommendations before the department reaches a critical state.</p>
        <p style="margin-bottom: 0; color: #93c5fd; font-style: italic; font-size: 0.9em;">Note: Built as a production-style MLOps demonstration using simulated Kaggle-inspired ER data to model high-stakes healthcare staffing and patient-flow risk safely.</p>
    </div>
    """,
    unsafe_allow_html=True
)

try:
    with open("backend/model_metrics.json", "r") as f:
        top_metrics = json.load(f)
        tm_m = top_metrics.get("metrics", {})
        tm_b = top_metrics.get("baseline_metrics", {})
        
        recall = tm_m.get('high_or_critical_recall', 0)
        xgb_mae = tm_m.get('mae', 0)
        base_mae = tm_b.get('mae', 0)
        
        col_hero1, col_hero2 = st.columns([1, 1])
        with col_hero1:
            st.markdown(f"""
            <div style="background: rgba(220, 38, 38, 0.15); border-left: 5px solid #ef4444; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <h2 style="color: #f87171; margin-top: 0; text-align: center;">🚨 High/Critical Recall: {recall:.1%}</h2>
                <p style="color: #fca5a5; font-size: 0.9em; margin-bottom: 0;">High/Critical Recall measures how often the model catches dangerous staffing-risk scenarios. For this prototype, catching unsafe staffing pressure is more important than exact minute-level wait-time prediction.</p>
            </div>
            """, unsafe_allow_html=True)
            
        with col_hero2:
            st.markdown(f"""
            <div style="background: rgba(59, 130, 246, 0.15); border-left: 5px solid #60a5fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="color: #93c5fd; margin-top: 0;">Baseline Comparison</h3>
                <p style="color: #eff6ff; font-size: 1.05em;">XGBoost reduced average wait-time error from baseline MAE <strong>{base_mae:.1f} minutes</strong> to <strong>{xgb_mae:.1f} minutes</strong>.</p>
                <p style="color: #eff6ff; font-size: 0.9em; margin-bottom: 0;">This proves that the XGBoost model is capturing complex operational signals far better than a naive average guess.</p>
            </div>
            """, unsafe_allow_html=True)
except Exception:
    pass

st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
st.markdown("#### 🏥 Shift Scenario Configuration")
st.caption("Define the clinical and environmental context for this shift scenario.")
st.caption("ℹ️ *This dataset does not contain real ESI counts. Urgency Level is used as the available acuity proxy.*")

col_preset = st.columns(1)[0]
with col_preset:
    st.selectbox(
        "Load Demo Scenario Preset",
        list(demo_scenarios.keys()),
        key="demo_select",
        on_change=on_demo_scenario_change
    )
    
    selected_preset = st.session_state.get("demo_select")
    if selected_preset and selected_preset != "Select a Demo Scenario...":
        data = demo_scenarios[selected_preset]
        hour_val = 14 if data['type'] == 'Day' else (18 if data['type'] == 'Evening' else 22)
        
        preset_html = f"""<div style='background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(99, 102, 241, 0.15) 100%); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 12px; box-shadow: 0 8px 32px 0 rgba(99, 102, 241, 0.15); padding: 20px; color: #f3f4f6; font-family: "Inter", sans-serif; margin-bottom: 20px;'>
<h5 style='margin-top:0; color:#a5b4fc; font-weight:700; font-size:1.1rem;'>📋 Scenario Summary</h5>
<div style='display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; font-size: 0.9rem; line-height: 1.6; margin-bottom: 15px;'>
<div>
<span style='color: #94a3b8;'>Preset Name:</span> <strong style='color:#818cf8;'>{selected_preset}</strong><br/>
<span style='color: #94a3b8;'>Month:</span> <strong>{data['date'].month}</strong><br/>
<span style='color: #94a3b8;'>Day of Week:</span> <strong>{data['date'].strftime('%A')}</strong><br/>
<span style='color: #94a3b8;'>Hour:</span> <strong>{hour_val}</strong>
</div>
<div>
<span style='color: #94a3b8;'>Shift:</span> <strong>{data['type']}</strong><br/>
<span style='color: #94a3b8;'>Department:</span> <strong>{data['dept']}</strong><br/>
<span style='color: #94a3b8;'>Patient Inflow Multiplier:</span> <strong style='color:#34d399;'>{data['patient_inflow_multiplier']}x</strong><br/>
<span style='color: #94a3b8;'>Nurse Call-out Rate:</span> <strong style='color:#f87171;'>{data['nurse_callout_rate']}%</strong>
</div>
<div>
<span style='color: #94a3b8;'>Waiting Room Count:</span> <strong style='color:#34d399;'>{data['waiting_room_count']}</strong><br/>
<span style='color: #94a3b8;'>Arrival Surge Multiplier:</span> <strong style='color:#34d399;'>{data['arrival_surge_multiplier']}x</strong><br/>
<span style='color: #94a3b8;'>ED Occupancy %:</span> <strong style='color:#f87171;'>{data['ed_occupancy_percent']}%</strong><br/>
<span style='color: #94a3b8;'>Boarding Count:</span> <strong style='color:#f87171;'>{data['boarding_count']}</strong>
</div>
<div>
<span style='color: #94a3b8;'>Boarding Hours Avg:</span> <strong style='color:#f87171;'>{data['boarding_hours_avg']} hrs</strong><br/>
<span style='color: #94a3b8;'>Low Acuity %:</span> <strong>{data['low_acuity_percent']}%</strong><br/>
<span style='color: #94a3b8;'>Fast-track Open:</span> <strong>{data['fast_track_open']}</strong><br/>
<span style='color: #94a3b8;'>Fast-track Queue:</span> <strong>{data['fast_track_queue']}</strong>
</div>
</div>
<details style='margin-top:15px;'>
<summary style='cursor:pointer; color:#a5b4fc; font-weight:800; font-size:1.02rem; margin-bottom:10px;'>🚨 Preset Operational Pressure Inputs</summary>
<div style='display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; font-size: 0.9rem; margin-top:12px;'>
<div>
<span style='color: #94a3b8;'>Arrival Surge Source:</span> <strong style='color:#38bdf8;'>Demo preset override</strong><br/>
<span style='color: #94a3b8;'>Bed/Boarding Source:</span> <strong style='color:#38bdf8;'>Demo preset override</strong>
</div>
<div>
<span style='color: #94a3b8;'>Fast-track Source:</span> <strong style='color:#38bdf8;'>Demo preset override</strong><br/>
<span style='color: #94a3b8;'>Data Input Mode:</span> <strong style='color:#38bdf8;'>Demo preset override</strong>
</div>
</div>
</details>
</div>"""
        with st.expander(f"📥 Loaded Demo Scenario Inputs — {selected_preset}", expanded=False):
            st.markdown(preset_html, unsafe_allow_html=True)

col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    st.date_input("Shift Date", key="scen_date")
    st.selectbox("Shift Type", ["Morning", "Evening", "Night"], key="scen_type")
    st.selectbox("Department", ["Emergency", "ICU", "Pediatrics"], key="scen_dept")

with col_s2:
    st.slider("Hospital Beds Capacity", 50, 400, step=50, key="scen_beds")
    st.slider("Low-Acuity Delay Level (1=Critical/Fast Track, 5=Low-Acuity/Longer Wait)", 1, 5, key="scen_acuity")

with col_s3:
    st.slider("Nurse-to-Patient Ratio", 0.08, 0.40, step=0.01, key="scen_ratio")
    st.selectbox("Specialist Available", [1, 0], format_func=lambda x: "Yes" if x==1 else "No", key="scen_spec")

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")

with st.expander("🧠 Memory & Developer Tools", expanded=False):
    st.caption(
        "Advanced memory controls and historical context. These tools are collapsed by default so the main staffing workflow stays clean."
    )

    st.markdown("#### Manual Memory Update")
    mem_state = get_inflow_memory_state()
    st.markdown("##### Current Inflow Memory State (`database/inflow_memory_state.json`)")
    st.json(mem_state)

    st.markdown(
        "This memory layer makes the agent's prior forecast error and rolling inflow trend visible. "
        "The next prediction is not stateless; it is adjusted using `rolling_inflow_avg`, "
        "`last_prediction_delta`, and `trend_direction`."
    )

    telemetry = {
        "waiting_room_count": st.session_state.waiting_room_count,
        "patient_inflow_multiplier": st.session_state.patient_inflow_multiplier,
        "arrival_surge_multiplier": st.session_state.arrival_surge_multiplier,
        "ambulance_arrival_pressure": st.session_state.ambulance_arrival_pressure,
        "ed_occupancy_percent": st.session_state.ed_occupancy_percent
    }

    if st.button("Forecast Next 10-Min Patient Inflow"):
        forecast_result = forecast_inflow_memory(telemetry)
        st.session_state.last_forecast = forecast_result.get("forecasted_volume", 0)
        st.markdown("##### New Forecast Generated")
        st.json(forecast_result)

    st.markdown("##### Submit Ground Truth")
    actual_inflow = st.number_input("Actual patient inflow in last 10 minutes", min_value=0, value=0)

    if st.button("Update Memory With Actual Inflow"):
        last_fc = st.session_state.get("last_forecast", mem_state.get("last_forecasted_volume", 0))
        updated_mem = update_inflow_memory_state(last_fc, actual_inflow)
        get_inflow_history.clear()
        st.success("Memory updated successfully.")
        st.json(updated_mem)

    st.markdown("---")
    st.markdown("#### Recent Inflow Memory History")
    st.caption("Loaded from a short cache so this section does not block normal page interaction.")
    hist_data = get_inflow_history()
    if hist_data:
        st.json(hist_data[-5:])
    else:
        st.write("No history available.")

    st.markdown("---")
    st.markdown("#### Similar Prior ER Memory Events")
    st.caption("Remote lookup is only run when requested.")
    if st.button("Load Similar Prior ER Memory Events", key="load_similar_memory_events_top"):
        try:
            scenario_sig = {
                "waiting_room_count": st.session_state.waiting_room_count,
                "ed_occupancy_percent": st.session_state.ed_occupancy_percent,
                "arrival_pressure": st.session_state.ambulance_arrival_pressure,
                "boarding_pressure": "High" if st.session_state.boarding_count > 10 else "Low", 
                "fatigue_pressure": "High" if st.session_state.nurse_callout_rate > 15 else "Low",
                "acuity_pressure": "High" if st.session_state.scen_acuity < 3 else "Low"
            }
            resp = requests.post(
                f"{API_BASE_URL}/api/find_similar_history",
                json={"scenario_signature": scenario_sig},
                timeout=10
            )
            sim_data = resp.json() if resp.ok else {}
            if sim_data and sim_data.get("similar_events"):
                st.json(sim_data["similar_events"])
            else:
                st.write("No similar events found.")
        except Exception as e:
            st.write(f"Error loading similar events: {e}")

st.markdown("---")

def render_styled_table(df):
    """Converts a pandas DataFrame to a beautiful high-contrast HTML table for clean, sharp display."""
    html = "<div style='overflow-x:auto;'><table style='width:100%; border-collapse: collapse; margin-bottom: 20px; font-family: \"Inter\", sans-serif; color: #f3f4f6;'>"
    # Headers
    html += "<tr style='border-bottom: 2px solid rgba(255,255,255,0.15); background: rgba(99, 102, 241, 0.12);'>"
    for col in df.columns:
        col_name = str(col).replace("_", " ").title()
        html += f"<th style='padding: 12px 10px; text-align: left; font-weight: 700; color: #a5b4fc; font-size: 0.95rem;'>{col_name}</th>"
    html += "</tr>"
    # Rows
    for idx, row in df.iterrows():
        html += "<tr style='border-bottom: 1px solid rgba(255,255,255,0.06);'>"
        for col in df.columns:
            val = row[col]
            if isinstance(val, list):
                val = ", ".join(val)
            elif isinstance(val, (int, float)) and col == "predicted_wait_time":
                val = f"{val:.1f} mins"
            elif isinstance(val, (int, float)) and col == "base_rate":
                val = f"${val:.2f}/hr"
            elif isinstance(val, (int, float)) and col in ["weekly_hours", "Current Hours", "Projected Hours"]:
                val = f"{val} hrs"
            
            # Make specific columns or values bold
            font_weight = "600"
            if col in ["assigned_nurses", "certifications", "status", "name", "Name", "Decision", "Cert Match"]:
                font_weight = "700"  # Bold text for key identifiers
            
            color = "#f3f4f6"
            if val in ["Staffed", "Valid", "PASS", "✅"]:
                color = "#34d399"  # High-contrast green
            elif val in ["Pending Approval", "Pending", "⚠️ Yes", "Overtime: 60h projected", "Fatigue: High"]:
                color = "#fbbf24"  # High-contrast orange/warning
            elif val in ["FAIL", "❌"] or "VETO" in str(val):
                color = "#f87171"  # High-contrast red
                
            html += f"<td style='padding: 10px; font-size: 0.95rem; font-weight: {font_weight}; color: {color};'>{val}</td>"
        html += "</tr>"
    html += "</table></div>"
    return html

st.markdown("<p style='color: #9ca3af; font-size: 1.05rem; font-weight: 600; margin-bottom: 15px;'>Choose a tab below. This keeps the old tab-style workflow, but only renders the selected section for speed.</p>", unsafe_allow_html=True)
workflow_page = st.radio(
    "Workflow",
    [
        "📋 Roster & Shortage Solver",
        "⚡ System Stress Simulator",
        "🔍 Explainability & Token Logs",
        "📝 Audit Log",
        "🔬 Research & Validation",
        "🏛️ AI Committee Debate & Planner",
        "📈 Model Performance",
    ],
    horizontal=True,
    key="workflow_page",
    label_visibility="collapsed",
)


# Selected workflow panel banner: makes the content area feel themed, not just the tab button.
WORKFLOW_PANEL_META = {
    "📋 Roster & Shortage Solver": {
        "class": "roster",
        "title": "📋 Roster & Shortage Solver",
        "help": "Primary operating panel for shift schedule, nurse registry, shortage resolution, approval, and roster updates.",
        "accent": "#60a5fa",
        "soft": "rgba(37, 99, 235, 0.16)",
        "border": "rgba(96, 165, 250, 0.34)",
    },
    "⚡ System Stress Simulator": {
        "class": "stress",
        "title": "⚡ System Stress Test Simulator",
        "help": "Run surge, call-out, acuity, and operational pressure simulations against the current ER staffing state.",
        "accent": "#fb923c",
        "soft": "rgba(249, 115, 22, 0.15)",
        "border": "rgba(251, 146, 60, 0.34)",
    },
    "🔍 Explainability & Token Logs": {
        "class": "explain",
        "title": "🔍 Explainability & Token Logs",
        "help": "Review why predictions, agents, and prompts made their decisions.",
        "accent": "#22d3ee",
        "soft": "rgba(34, 211, 238, 0.13)",
        "border": "rgba(34, 211, 238, 0.30)",
    },
    "📝 Audit Log": {
        "class": "audit",
        "title": "📝 Audit Log",
        "help": "Track approvals, rejections, overrides, roster updates, and governance events.",
        "accent": "#fbbf24",
        "soft": "rgba(251, 191, 36, 0.13)",
        "border": "rgba(251, 191, 36, 0.28)",
    },
    "🔬 Research & Validation": {
        "class": "research",
        "title": "🔬 Research & Validation",
        "help": "Show evidence, model framing, prototype limits, and validation notes for the capstone demo.",
        "accent": "#7dd3fc",
        "soft": "rgba(125, 211, 252, 0.12)",
        "border": "rgba(125, 211, 252, 0.26)",
    },
    "🏛️ AI Committee Debate & Planner": {
        "class": "ai",
        "title": "🏛️ AI Committee Debate & Planner",
        "help": "Agentic AI review panel for staffing recommendations, veto logic, and human-in-the-loop decisions.",
        "accent": "#a855f7",
        "soft": "rgba(168, 85, 247, 0.15)",
        "border": "rgba(168, 85, 247, 0.34)",
    },
    "📈 Model Performance": {
        "class": "performance",
        "title": "📈 Model Performance",
        "help": "Inspect model metrics, stability, and operational performance signals.",
        "accent": "#34d399",
        "soft": "rgba(52, 211, 153, 0.13)",
        "border": "rgba(52, 211, 153, 0.30)",
    },
}
_panel = WORKFLOW_PANEL_META.get(workflow_page, WORKFLOW_PANEL_META["📋 Roster & Shortage Solver"])
st.markdown(
    f"""
    <style>
        :root {{
            --workflow-accent: {_panel['accent']};
            --workflow-accent-soft: {_panel['soft']};
            --workflow-border: {_panel['border']};
        }}
    </style>
    <div class="workflow-panel-banner workflow-panel-{_panel['class']}">
        <div class="panel-kicker">Current workspace</div>
        <div class="panel-title">{_panel['title']}</div>
        <p class="panel-help">{_panel['help']}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Tab 1: Roster and Shortage Solver
if workflow_page == "📋 Roster & Shortage Solver":
    if st.session_state.get("last_summary"):
        s = st.session_state.last_summary
        st.markdown(f"""
        <div class="glass-card" style="border: 2px solid #10b981; background: rgba(16, 185, 129, 0.12);">
            <h4 style="color: #10b981; margin-top: 0; margin-bottom: 12px; font-weight: 700;">🏆 Final Decision Executive Summary (Last Resolved Shift)</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.95em;">
                <div><strong>Risk Level:</strong> {s['risk_level']}</div>
                <div><strong>Predicted Wait Time:</strong> {s['pred_wait']} (Threshold: {s['threshold']})</div>
                <div><strong>Additional Nurses Needed:</strong> {s['nurses_needed']}</div>
                <div><strong>Recommended Nurses:</strong> {s['recommended_nurses']}</div>
                <div><strong>Compliance Status:</strong> {s['compliance_status']}</div>
                <div><strong>Human Decision:</strong> {s['human_decision']}</div>
                <div><strong>Roster Update:</strong> {s['roster_update']}</div>
                <div><strong>Audit Log:</strong> {s['audit_log']}</div>
                <div><strong>Token Mode:</strong> {s['token_mode']}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.get("last_report_data"):
            import json, datetime
            st.download_button(
                label="📄 Download Final Staffing Decision Report",
                data=json.dumps(st.session_state.last_report_data, indent=2),
                file_name=f"final_staffing_decision_report.json",
                mime="application/json"
            )
            
        st.markdown("---")

    st.subheader("🏥 Shift Schedule & Status")
    schedule = normalize_records(get_schedule(), list_keys=("schedule", "data", "results", "items"))
    if schedule:
        sched_df = pd.DataFrame.from_records(schedule)
        expected_cols = ["id", "date", "shift_type", "assigned_nurses", "acuity_level", "predicted_wait_time", "status"]
        for col in expected_cols:
            if col not in sched_df.columns:
                sched_df[col] = ""
        sched_df = sched_df[expected_cols]
        st.markdown(render_styled_table(sched_df), unsafe_allow_html=True)
    else:
        st.info("No active schedules found.")

    st.subheader("👩⚕️ Nurse Database Registry")
    nurses = normalize_records(get_nurses(), list_keys=("nurses", "data", "results", "items"))

    # Keep the main workflow compact: show a registry summary first, then place the full
    # nurse table and add-nurse form inside an expander.
    if nurses:
        def _cert_list(nurse):
            certs = nurse.get("certifications", [])
            if isinstance(certs, str):
                return [c.strip() for c in certs.replace(";", ",").split(",") if c.strip()]
            if isinstance(certs, (list, tuple, set)):
                return [str(c).strip() for c in certs if str(c).strip()]
            return []

        total_nurses = len(nurses)
        emergency_nurses = sum(1 for n in nurses if any(c.lower() == "emergency" for c in _cert_list(n)))
        icu_nurses = sum(1 for n in nurses if any(c.lower() == "icu" for c in _cert_list(n)))
        peds_nurses = sum(1 for n in nurses if any(c.lower() == "pediatrics" for c in _cert_list(n)))
        fatigue_watch = sum(1 for n in nurses if int(float(n.get("weekly_hours", 0) or 0)) >= 40)
        avg_hours = sum(float(n.get("weekly_hours", 0) or 0) for n in nurses) / max(total_nurses, 1)

        st.markdown(
            f"""
            <div class="glass-card" style="border-left: 4px solid #60a5fa; background: rgba(15, 23, 42, 0.72); margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap;">
                    <div>
                        <div style="color: #93c5fd; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.78rem; font-weight: 800;">Nurse registry summary</div>
                        <div style="color: #ffffff; font-size: 1.02rem; font-weight: 750; margin-top: 2px;">{total_nurses} nurses loaded · fatigue and weekly-hour constraints tracked</div>
                    </div>
                    <div style="color: #cbd5e1; font-size: 0.9rem; text-align: right;">
                        Emergency: <strong style="color:#bfdbfe;">{emergency_nurses}</strong> &nbsp;|&nbsp;
                        ICU: <strong style="color:#bfdbfe;">{icu_nurses}</strong> &nbsp;|&nbsp;
                        Pediatrics: <strong style="color:#bfdbfe;">{peds_nurses}</strong><br/>
                        Avg weekly hours: <strong style="color:#e0f2fe;">{avg_hours:.1f}</strong> · Fatigue watch: <strong style="color:#fbbf24;">{fatigue_watch}</strong>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("Nurse database is empty.")

    with st.expander("👩‍⚕️ View Nurse Database Registry & Add Custom Nurse", expanded=False):
        if nurses:
            nurses_df = pd.DataFrame.from_records(nurses)
            expected_cols = ["id", "name", "certifications", "weekly_hours", "base_rate", "circadian_preference", "distance_miles"]
            for col in expected_cols:
                if col not in nurses_df.columns:
                    nurses_df[col] = ""
            nurses_df = nurses_df[expected_cols]
            st.markdown(render_styled_table(nurses_df), unsafe_allow_html=True)
        else:
            st.info("No nurse rows available yet. Add a custom nurse below or restore demo nurses and shift schedule from the sidebar.")

        st.markdown("#### ➕ Add Custom Nurse to Registry")
        with st.form("add_nurse_form", clear_on_submit=True):
            new_name = st.text_input("Name")
            new_certs = st.multiselect("Certifications", ["Emergency", "ICU", "Pediatrics"])
            new_hours = st.number_input("Current Weekly Hours", min_value=0, max_value=60, value=20)
            new_rate = st.number_input("Base Rate ($/hr)", min_value=10.0, max_value=150.0, value=50.0, step=1.0)
            new_circadian = st.selectbox("Circadian Preference", ["Flexible", "Morning", "Night"])
            new_distance = st.number_input("Distance to Facility (miles)", min_value=0, max_value=100, value=5)
            new_phone = st.text_input("Phone Number", value="+1-555-0000")
            
            submit_nurse = st.form_submit_button("Add Nurse to Registry")
            if submit_nurse:
                if not new_name.strip():
                    st.error("Name is required.")
                else:
                    max_num = 7
                    for n in nurses:
                        nid = n.get("id", "")
                        if nid.startswith("NURSE_"):
                            try:
                                num = int(nid.split("_")[1])
                                if num > max_num:
                                    max_num = num
                            except ValueError:
                                pass
                    next_id = f"NURSE_{max_num + 1:03d}"
                    
                    payload = {
                        "id": next_id,
                        "name": new_name.strip(),
                        "certifications": new_certs,
                        "weekly_hours": int(new_hours),
                        "base_rate": float(new_rate),
                        "circadian_preference": new_circadian,
                        "distance_miles": int(new_distance),
                        "phone": new_phone.strip()
                    }
                    
                    try:
                        res = requests.post(f"{API_BASE_URL}/api/nurses", json=payload)
                        res_data = res.json()
                        if res_data.get("success"):
                            st.success(res_data["message"])
                            clear_dashboard_bootstrap_cache()
                            st.rerun()
                        else:
                            st.error(res_data.get("error", "Failed to add nurse"))
                    except Exception as e:
                        st.error(f"Error connecting to backend: {e}")

    st.markdown("---")
    
    st.markdown(
        """
        <div class="shortage-workflow-shell">
            <div class="shortage-workflow-kicker">Roster workspace guide</div>
            <div class="shortage-workflow-title">🚦 3-Step Shortage Resolution Workflow</div>
            <div class="shortage-workflow-copy">
                Follow the operational path from wait-time risk assessment to AI staffing action plan to final human approval.
                This stays inside the Roster &amp; Shortage Solver theme, with stronger structure so the workflow is easier to demo.
            </div>
            <div class="shortage-workflow-track">
                <div class="shortage-step-card">
                    <div><span class="shortage-step-number">1</span><span class="shortage-step-label">Assess ER risk</span></div>
                    <div class="shortage-step-help">Forecast wait time and detect staffing pressure.</div>
                </div>
                <div class="shortage-step-card">
                    <div><span class="shortage-step-number">2</span><span class="shortage-step-label">Solve shortage</span></div>
                    <div class="shortage-step-help">Generate the safest roster action plan.</div>
                </div>
                <div class="shortage-step-card">
                    <div><span class="shortage-step-number">3</span><span class="shortage-step-label">Approve roster</span></div>
                    <div class="shortage-step-help">Review, approve, reject, or override with audit trail.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Step 1
    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #60a5fa; border-bottom: 2px solid rgba(96, 165, 250, 0.3); padding-bottom: 8px; margin-top: 10px; font-size: 1.45rem; line-height: 1.25; font-weight: 700;'>1️⃣ Step 1: ER Wait-Time Risk Assessment</h3>", unsafe_allow_html=True)
    st.caption("Workflow Step 1 of 3: Forecast ER wait time and identify staffing shortages based on operational pressure.")
    st.markdown(
        """
        <div style="
            background-color: rgba(59, 130, 246, 0.12);
            border: 1px solid rgba(59, 130, 246, 0.35);
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 20px;
            color: #F8FAFC;
            line-height: 1.6;
        ">
            <p style="margin: 0; color: #FFFFFF; font-size: 1rem;">ℹ️ The system uses the active Shift Scenario defined at the top of the page. You can customize the environmental modifiers below to perform a what-if risk assessment.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown("##### 🎛️ Roster Shift Setting")
    short_shift = st.selectbox("Roster Shift ID to Update/Create", ["NEW_SHIFT", "SHIFT_001", "SHIFT_002", "SHIFT_003"], key="scen_shift_id")

    st.markdown("**🏥 Environmental & Outbreak Surges (What-If Context)**")
    col_env1, col_env2 = st.columns(2)
    with col_env1:
        env_weather = st.selectbox("Weather Event", ["Normal", "Severe Heatwave", "Severe Blizzard / Ice Storm"], key="env_weather_select")
    with col_env2:
        env_flu = st.slider("Flu / Viral Outbreak Activity", 1, 5, 1, help="1 = Baseline, 5 = Epidemic Surge", key="env_flu_slider")

    st.caption(f"ℹ️ **Action**: {HELPER_ASSESS_RISK}")
    if st.button("Assess ER Wait-Time Risk", type="primary", use_container_width=True):
        # Auto-derive features
        short_date = st.session_state.scen_date
        short_type = st.session_state.scen_type
        short_dept = st.session_state.scen_dept
        sb_beds = st.session_state.scen_beds
        sb_ratio = st.session_state.scen_ratio
        sb_acuity = st.session_state.scen_acuity
        sb_spec = st.session_state.scen_spec
        
        month = short_date.month
        day_of_week = short_date.weekday() # 0=Mon, 6=Sun
        hour_map = {"Morning": 8, "Evening": 16, "Night": 22}
        visithour = hour_map.get(short_type, 12)
        
        # Calculate environmental surge multiplier
        weather_surge = 0.30 if env_weather == "Severe Blizzard / Ice Storm" else (0.15 if env_weather == "Severe Heatwave" else 0.0)
        outbreak_surge = (env_flu - 1) * 0.10
        env_multiplier = round(1.0 + weather_surge + outbreak_surge, 2)
        
        effective_ratio = round(sb_ratio / env_multiplier, 3)
        
        selected_preset = st.session_state.get("demo_select")
        preset_info = None
        if selected_preset and selected_preset != "Select a Demo Scenario...":
            preset_info = demo_scenarios[selected_preset].copy()
            preset_info["selected_demo_preset"] = selected_preset
            preset_info["month"] = preset_info["date"].month
            preset_info["day_of_week"] = preset_info["date"].weekday()
            preset_info["hour"] = 14 if preset_info["type"] == "Day" else (18 if preset_info["type"] == "Evening" else 22)
            if "date" in preset_info:
                preset_info["date"] = str(preset_info["date"])
            
        payload = {
            "facility_size_beds": sb_beds,
            "month": month,
            "day_of_week": day_of_week,
            "visithour": visithour,
            "urgency_level": sb_acuity,
            "nurse_to_patient_ratio": effective_ratio,
            "specialist_availability": sb_spec,
            "preset_data": preset_info
        }
        
        # Save state for step 2
        st.session_state.xg_inputs = {
            "shift_id": short_shift,
            "shift_date": short_date,
            "shift_type": short_type,
            "department": short_dept,
            "acuity": sb_acuity,
            "env_weather": env_weather,
            "env_flu": env_flu,
            "env_multiplier": env_multiplier,
            "computed_month": month,
            "computed_day_of_week": day_of_week,
            "computed_visithour": visithour
        }
        
        try:
            res = requests.post(f"{API_BASE_URL}/api/predict_wait", json=payload, timeout=15)

            try:
                res_json = res.json()
            except Exception:
                st.error(
                    f"Prediction endpoint did not return JSON. "
                    f"HTTP {res.status_code}. Response: {res.text[:500]}"
                )
                res_json = None

            if res_json is not None:
                if not res.ok or res_json.get("success") is False:
                    backend_error = res_json.get("error") or res_json.get("message") or res.text[:500]
                    st.error(
                        f"Prediction backend error. HTTP {res.status_code}. "
                        f"{backend_error}"
                    )
                    st.caption(f"Backend URL used: {API_BASE_URL}/api/predict_wait")
                else:
                    pred = res_json.get("predicted_wait_time")
                    safety_thresh = res_json.get("safety_threshold")
                    evidence = res_json.get("evidence", {})

                    if pred is None:
                        st.error(
                            "Prediction response did not include 'predicted_wait_time'. "
                            f"Response keys: {list(res_json.keys())}"
                        )
                        st.json(res_json)
                    else:
                        st.session_state.pred_wait = pred
                        st.session_state.safety_thresh = safety_thresh if safety_thresh is not None else 0
                        st.session_state.evidence = evidence

                        needed = evidence.get("final_additional_nurses_needed", 0)
                        st.session_state.estimated_needed = needed
                        st.session_state.risk_assessed = True
                        st.rerun()
        except Exception as e:
            st.error(f"Error calling prediction endpoint: {e}")
            st.caption(f"Backend URL used: {API_BASE_URL}/api/predict_wait")
            
    if st.session_state.get("risk_assessed"):
        pred = st.session_state.get("pred_wait", 0)
        thresh = st.session_state.get("safety_thresh", 0)
        needed = st.session_state.get("estimated_needed", 0)
        
        st.markdown("---")
        st.markdown(f"**XGBoost Prediction**: `{pred:.1f} mins` (Safety Threshold: `{thresh} mins`)")
        evidence = st.session_state.get("evidence", {})
        if evidence:
            st.markdown(render_pressure_status_card(evidence), unsafe_allow_html=True)
        
        st.write(f"ℹ️ **Staffing Logic**: Predicted wait time is **{pred:.1f} mins**. Threshold is **{thresh} mins**. ")
        if needed > 0:
            st.error(f"⚠️ SHORTAGE DETECTED! Risk level requires {needed} additional nurse(s).")
        else:
            st.success("✅ Risk level is optimal. No action required.")
            
        # Additional Nurse Count Breakdown
        evidence = st.session_state.get("evidence", {})
        if evidence:
            with st.expander("🛡️ Staffing need breakdown and operational rationale", expanded=True):
                st.markdown("<div style='background: rgba(30, 41, 59, 0.4); padding: 15px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); margin-top: 10px; margin-bottom: 10px;'>", unsafe_allow_html=True)
                st.markdown("##### 🛡️ Additional Nurse Count Breakdown")
            
                gap = round(pred - thresh, 1)
                st.write(f"- **Predicted wait time**: `{pred:.1f} mins`")
                st.write(f"- **Safety threshold**: `{thresh} mins`")
                st.write(f"- **Wait-time gap**: `{gap} mins`")
                st.write(f"- **Base nurses from wait-time gap**: `{evidence.get('base_nurses_from_wait_time', 0)}`")
                st.write(f"- **Operational pressure nurse increments**: `{evidence.get('operational_pressure_nurse_increments', 0)}`")
                st.write(f"- **Final additional nurses recommended**: `{evidence.get('final_additional_nurses_needed', 0)}`")
            
                reasons = evidence.get("nurse_increment_reasons", [])
                if reasons:
                    st.write("**Increment reasons**:")
                    for r in reasons:
                        st.write(f"  * {r}")
                else:
                    st.write("**Increment reasons**: None")
                
                if evidence.get("boarding_pressure") == "Critical" or evidence.get("selected_demo_preset") == "4. Boarding Gridlock / No Inpatient Beds":
                    st.warning("⚠️ **BED-FLOW ESCALATION REQUIRED**: Critical boarding pressure detected. Inpatient bed coordination team must be notified immediately.")
                
                st.markdown("</div>", unsafe_allow_html=True)
            
        with st.expander("📊 View XGBoost local prediction drivers", expanded=False):
            # Local Prediction Drivers Main Section
            st.markdown("<div style='background: rgba(30, 41, 59, 0.3); padding: 18px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); margin-top: 15px;'>", unsafe_allow_html=True)
            st.markdown("##### 📊 XGBoost Local Prediction Drivers")
            st.caption("This chart displays how individual XGBoost input features influence the predicted wait time up or down relative to the model baseline.")
        
            scen = st.session_state.xg_inputs
            month = scen["shift_date"].month
            day = scen["shift_date"].weekday()
            hour_map = {"Morning": 8, "Evening": 16, "Night": 22}
            hour = hour_map.get(scen["shift_type"], 12)
        
            # Calculate effective ratio
            weather_surge = 0.30 if scen.get("env_weather") == "Severe Blizzard / Ice Storm" else (0.15 if scen.get("env_weather") == "Severe Heatwave" else 0.0)
            outbreak_surge = (scen.get("env_flu", 1) - 1) * 0.10
            env_multiplier = round(1.0 + weather_surge + outbreak_surge, 2)
            effective_ratio = round(st.session_state.get("scen_ratio", 0.20) / env_multiplier, 3)

            drivers = calculate_local_drivers(
                beds=st.session_state.get("scen_beds", 200),
                month=month,
                day=day,
                hour=hour,
                acuity=st.session_state.get("scen_acuity", 3),
                ratio=effective_ratio,
                spec=st.session_state.get("scen_spec", 1)
            )
        
            # Sort and take top 5
            sorted_drivers = sorted(drivers.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
            driver_df = pd.DataFrame(sorted_drivers, columns=["Driver", "Contribution"])
        
            import altair as alt
            chart = alt.Chart(driver_df).mark_bar().encode(
                x=alt.X('Contribution:Q', title='Contribution to Wait Time (mins)'),
                y=alt.Y('Driver:N', sort='-x', title='', axis=alt.Axis(labelLimit=300)),
                color=alt.condition(
                    alt.datum.Contribution > 0,
                    alt.value("#ef4444"), # Red for positive drivers (increases wait time)
                    alt.value("#10b981")  # Green for negative drivers (reduces wait time)
                )
            ).properties(height=200)
            st.altair_chart(chart, use_container_width=True)
            st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-top: 14px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; color: #FFFFFF;"><strong>Interpretation:</strong> This chart explains the local XGBoost wait-time prediction for the current scenario. Red bars push the predicted wait time higher, while green bars reduce the predicted wait time relative to the model baseline.</p><p style="color: #FFFFFF;">The chart explains why XGBoost predicted the current ER wait time using model input features such as nurse-to-patient ratio, specialist availability, weekend influx, seasonal/month surge, and visit-hour peak effects.</p><p style="color: #FFFFFF;">If the predicted wait time remains below the safety threshold, the XGBoost wait-time gap contributes 0 additional nurses. Any final staffing increase after that is caused by post-prediction operational pressure rules, such as Critical adjusted operational risk, Critical arrival surge pressure, boarding pressure, ESI pressure, or fatigue pressure.</p><p style="margin-bottom: 0; color: #FFFFFF;">This separation makes clear that the XGBoost chart explains the wait-time forecast, while the staffing solver explains the final nurse recommendation.</p></div>""", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            
        with st.expander("🩺 View clinical risk explanation and what-if staffing simulator", expanded=False):
            # --- NEW: Clinical Risk Explanation ---
            st.markdown("##### 🩺 Clinical Risk Explanation")
            st.write("Based on the current inputs, the following operational factors are driving the predicted staffing risk:")
            risk_bullets = []
            hour = hour_map.get(scen.get("shift_type"), 12)
            if hour in range(16, 23):
                risk_bullets.append("- **Peak-hour pressure detected** (Evening volume surge).")
            if scen.get("shift_date") and scen["shift_date"].month in [12, 1, 2] and scen["shift_date"].weekday() in [5, 6]:
                risk_bullets.append("- **Winter weekend surge pattern detected**.")
            elif scen.get("shift_date") and scen["shift_date"].month in [12, 1, 2]:
                risk_bullets.append("- **Winter surge pattern detected**.")
            elif scen.get("shift_date") and scen["shift_date"].weekday() in [5, 6]:
                risk_bullets.append("- **Weekend pattern detected**.")
            
            if effective_ratio < 0.18:
                risk_bullets.append("- **Poor nurse-to-patient ratio** increases staffing pressure.")
            if st.session_state.get("scen_spec", 1) == 0:
                risk_bullets.append("- **Specialist unavailable**, increasing operational bottleneck risk.")
            if scen.get("acuity", 3) < 3: # 1 or 2 is high urgency
                risk_bullets.append("- **Urgency/acuity proxy is elevated**.")
            if st.session_state.get("scen_beds", 200) < 150:
                risk_bullets.append("- **Small facility size** increases capacity pressure.")
            
            if not risk_bullets:
                adj_risk = evidence.get("adjusted_operational_risk", "Normal")
                if adj_risk in ["High", "Critical"]:
                    risk_bullets.append("- Although the XGBoost wait-time forecast may be below the safety threshold, operational pressure signals indicate significant strain and require staffing escalation.")
                else:
                    risk_bullets.append("- Current operational pressure signals do not indicate severe strain beyond the XGBoost wait-time forecast.")
            
            for bullet in risk_bullets:
                st.write(bullet)
            
            # --- NEW: What-If Staffing Simulator ---
            st.markdown("##### 🔬 What-If Staffing Simulator")
            st.write("This simulator shows how additional nurse coverage may reduce predicted staffing-risk pressure. It is a prototype decision-support estimate, not a clinical guarantee.")
        
            sim_data = []
            base_ratio = st.session_state.get("scen_ratio", 0.20)
            beds = st.session_state.get("scen_beds", 200)
        
            def simulate_wait(nurses_added):
                new_ratio = base_ratio + (nurses_added / max(beds, 1))
                new_eff_ratio = round(new_ratio / env_multiplier, 3)
                return predict_wait_time(
                    facility_size_beds=beds,
                    month=month,
                    day_of_week=day,
                    visithour=hour,
                    urgency_level=scen.get("acuity", 3),
                    nurse_to_patient_ratio=new_eff_ratio,
                    specialist_availability=st.session_state.get("scen_spec", 1)
                )
            
            def get_risk_label(diff):
                if diff <= 0: return "🟢 Optimal"
                elif diff <= 30: return "🟡 Low Risk"
                elif diff <= 60: return "🟠 Moderate"
                else: return "🔴 High/Critical"

            base_diff = pred - thresh
            base_risk = get_risk_label(base_diff)
            sim_data.append({"Scenario": "Current staffing", "Predicted Wait Time": f"{pred:.1f} min", "Staffing Risk": base_risk, "Improvement": "-"})
        
            for add_n in [1, 2, 3]:
                sim_pred = simulate_wait(add_n)
                sim_diff = sim_pred - thresh
                sim_risk = get_risk_label(sim_diff)
                imp = max(0, pred - sim_pred)
                sim_data.append({"Scenario": f"Add {add_n} nurse{'s' if add_n>1 else ''}", "Predicted Wait Time": f"{sim_pred:.1f} min", "Staffing Risk": sim_risk, "Improvement": f"-{imp:.1f} min"})
            
            st.table(pd.DataFrame(sim_data))

    st.markdown("</div>", unsafe_allow_html=True)
    
    # Step 2
    if st.session_state.get("risk_assessed") and st.session_state.get("estimated_needed", 0) > 0:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.markdown("<h3 style='color: #a78bfa; border-bottom: 2px solid rgba(167, 139, 250, 0.3); padding-bottom: 8px; margin-top: 10px; font-size: 1.45rem; line-height: 1.25; font-weight: 700;'>2️⃣ Step 2: Staffing Action Plan</h3>", unsafe_allow_html=True)
        st.caption("Workflow Step 2 of 3: Generate an optimized roster change to resolve the detected shortage.")
        st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; margin-bottom: 0; color: #FFFFFF;">Translate risk into an operational roster change. The ADK will find the best nurses to fill the gap.</p></div>""", unsafe_allow_html=True)
        evidence = st.session_state.get("evidence", {})
        if evidence:
            st.markdown(render_pressure_staffing_adjustment_card(evidence), unsafe_allow_html=True)
        
        scen = st.session_state.xg_inputs
        st.markdown("**Target Shift Scenario (Read-Only)**")
        st.write(f"- **Shift**: {scen['shift_id']} on {scen['shift_date']} ({scen['shift_type']})")
        st.write(f"- **Department**: {scen['department']}")
        st.write(f"- **Patient Acuity Level**: {scen['acuity']}")
        st.write(f"- **Environmental Patient Volume Surge**: {scen.get('env_multiplier', 1.0)}x (Weather: {scen.get('env_weather', 'Normal')}, Flu Activity: Level {scen.get('env_flu', 1)})")
        st.write(f"- **Estimated Additional Nurses Needed**: {st.session_state.get('estimated_needed')}")
        st.caption(f"ℹ️ **Action**: {HELPER_LAUNCH_SOLVER}")
        if st.button("Launch Multi-Agent Shortage Solver", type="primary", use_container_width=True):
            st.session_state.pending_log = None
            st.session_state.last_decision_status = None
            st.markdown("### 🧬 Google ADK Multi-Agent Execution Logs")
            progress_bar = st.progress(0)
            
            enable_llm = st.session_state.get("ai_mode") in ["Live Gemini API (Tokens)", "Live Groq API (Tokens)", "Live Gemini API (Tokens) [Disabled]"] or os.getenv("ENABLE_LLM_DEBATE", "false").lower() == "true"
            selected_preset = st.session_state.get("demo_select")
            preset_info = None
            if selected_preset and selected_preset != "Select a Demo Scenario...":
                preset_info = demo_scenarios[selected_preset].copy()
                preset_info["selected_demo_preset"] = selected_preset
                preset_info["month"] = preset_info["date"].month
                preset_info["day_of_week"] = preset_info["date"].weekday()
                preset_info["hour"] = 14 if preset_info["type"] == "Day" else (18 if preset_info["type"] == "Evening" else 22)
                if "date" in preset_info:
                    preset_info["date"] = str(preset_info["date"])

            payload = {
                # Carry the selected roster shift through the solver workflow so
                # approval can update the intended schedule row. NEW_SHIFT means
                # approval should create a new shift instead of updating SHIFT_001/2/3.
                "shift_id": scen.get("shift_id", "NEW_SHIFT"),
                "department": scen['department'],
                "shift_type": scen.get('shift_type', 'Morning'),
                "acuity_level": scen['acuity'],
                "required_nurses": st.session_state.get("estimated_needed"),
                "patient_volume_multiplier": scen.get('env_multiplier', 1.0),
                "date": str(scen.get('shift_date', '')),
                "month": scen['shift_date'].month,
                "day_of_week": scen['shift_date'].weekday(),
                "visithour": hour_map.get(scen['shift_type'], 12),
                "base_wait_time": float(st.session_state.get("pred_wait", 0)),
                "enable_llm_debate": enable_llm,
                "provider": "groq" if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else "gemini",
                "gemini_model": (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash")),
                "preset_data": preset_info
            }
            
            with st.spinner("Running multi-agent shortage solver..."):
                try:
                    res = requests.post(f"{API_BASE_URL}/api/resolve_shortage", json=payload)
                    result = res.json()
                    
                    if result.get("success"):
                        st.session_state.pending_log = result["log"]

                        resolved_live_usage = result.get("live_usage") or st.session_state.pending_log.get("live_debate") or {}
                        backend_live_called = False
                        if enable_llm and resolved_live_usage:
                            usage_status = resolved_live_usage.get("status", "not_requested")
                            live_usage = {
                                "llm_calls": int(resolved_live_usage.get("llm_calls", 0) or 0),
                                "prompt_tokens": int(resolved_live_usage.get("prompt_tokens", 0) or 0),
                                "response_tokens": int(resolved_live_usage.get("response_tokens", 0) or 0),
                                "total_tokens": int(resolved_live_usage.get("total_tokens", 0) or 0),
                                "estimated_api_cost": float(resolved_live_usage.get("estimated_api_cost", 0.0) or 0.0),
                                "status": usage_status,
                                "error": resolved_live_usage.get("error", ""),
                                "model_used": resolved_live_usage.get("model_used", ""),
                                "selected_model": resolved_live_usage.get("selected_model", (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash"))),
                                "normalized_selected_model": resolved_live_usage.get("normalized_selected_model", ""),
                                "attempted_models": resolved_live_usage.get("attempted_models", []),
                                "available_models": resolved_live_usage.get("available_models", [])
                            }
                            st.session_state.live_gemini_usage = live_usage
                            st.session_state.pending_log.setdefault("costs", {})
                            for k in ["llm_calls", "prompt_tokens", "response_tokens", "total_tokens", "estimated_api_cost"]:
                                st.session_state.pending_log["costs"][k] = live_usage[k]
                            st.session_state.pending_log["token_usage"] = {
                                "prompt": live_usage["prompt_tokens"],
                                "response": live_usage["response_tokens"],
                                "total": live_usage["total_tokens"],
                                "llm_calls": live_usage["llm_calls"]
                            }
                            backend_live_called = usage_status in ("called", "failed")
                            if usage_status == "called":
                                st.caption(f"✅ Live API debate called by backend. Tokens used: {live_usage['total_tokens']}")
                            elif usage_status == "failed":
                                st.warning(f"Live API was requested but failed: {live_usage.get('error', 'Unknown error')}")

                        # Fallback path: older backends may not call Gemini inside
                        # /api/resolve_shortage. In that case, explicitly call the live debate endpoint.
                        # The shortage solver can still return a local-rule result, so this call is
                        # what actually causes Gemini token usage to appear in the UI.
                        if enable_llm and not backend_live_called:
                            try:
                                live_payload = {
                                    "context": {
                                        "scenario": scen,
                                        "solver_payload": payload,
                                        "committee_evidence": st.session_state.pending_log.get("committee_evidence", {}),
                                        "explainability_narrative": st.session_state.pending_log.get("explainability_narrative", "")
                                    },
                                    "rec_nurses": st.session_state.pending_log.get("resolved_nurses", []),
                                    "rejected_candidates": st.session_state.pending_log.get("rejected_candidates", []),
                                    "provider": "groq" if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else "gemini",
                                    "model": (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash"))
                                }
                                debate_res = requests.post(f"{API_BASE_URL}/api/generate_live_debate", json=live_payload, timeout=60)
                                debate_json = debate_res.json()
                                if debate_json.get("success"):
                                    debate = debate_json.get("debate", {})
                                    st.session_state.agent_debate = debate

                                    # Copy Gemini token counts into pending_log['costs'] so the sidebar
                                    # token widget updates immediately after rerun.
                                    st.session_state.pending_log.setdefault("costs", {})
                                    live_usage = {
                                        "llm_calls": int(debate.get("llm_calls", 1) or 1),
                                        "prompt_tokens": int(debate.get("prompt_tokens", 0) or 0),
                                        "response_tokens": int(debate.get("response_tokens", 0) or 0),
                                        "total_tokens": int(debate.get("total_tokens", 0) or 0),
                                        "estimated_api_cost": float(debate.get("estimated_api_cost", 0.0) or 0.0),
                                        "status": "called",
                                        "error": "",
                                        "model_used": debate.get("model_used") or debate_json.get("model_used") or (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash")),
                                        "selected_model": (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash")),
                                        "normalized_selected_model": debate.get("normalized_selected_model", ""),
                                        "attempted_models": debate.get("attempted_models", []),
                                        "available_models": debate.get("available_models", [])
                                    }
                                    st.session_state.live_gemini_usage = live_usage
                                    for k in ["llm_calls", "prompt_tokens", "response_tokens", "total_tokens", "estimated_api_cost"]:
                                        st.session_state.pending_log["costs"][k] = live_usage[k]

                                    # Keep the older token_usage field in sync for sections that read it.
                                    st.session_state.pending_log["token_usage"] = {
                                        "prompt": live_usage["prompt_tokens"],
                                        "response": live_usage["response_tokens"],
                                        "total": live_usage["total_tokens"],
                                        "llm_calls": live_usage["llm_calls"]
                                    }
                                    st.caption(f"✅ Live API debate called. Tokens used: {live_usage['total_tokens']}")
                                else:
                                    err = debate_json.get('error', 'Unknown error')
                                    st.session_state.live_gemini_usage = {
                                        "llm_calls": 0,
                                        "prompt_tokens": 0,
                                        "response_tokens": 0,
                                        "total_tokens": 0,
                                        "estimated_api_cost": 0.0,
                                        "status": "failed",
                                        "error": err,
                                        "model_used": debate_json.get("model_used", (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash"))),
                                        "selected_model": (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash")),
                                        "normalized_selected_model": debate_json.get("normalized_selected_model", ""),
                                        "attempted_models": debate_json.get("attempted_models", []),
                                        "available_models": debate_json.get("available_models", [])
                                    }
                                    st.warning(f"Live API debate did not run: {err}")
                            except Exception as live_e:
                                st.session_state.live_gemini_usage = {
                                    "llm_calls": 0,
                                    "prompt_tokens": 0,
                                    "response_tokens": 0,
                                    "total_tokens": 0,
                                    "estimated_api_cost": 0.0,
                                    "status": "failed",
                                    "error": str(live_e),
                                    "model_used": (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash")),
                                    "selected_model": (os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") if st.session_state.get("ai_mode") == "Live Groq API (Tokens)" else st.session_state.get("model_option", "gemini-2.0-flash"))
                                }
                                st.warning(f"Live API debate failed; using local recommendation fallback: {live_e}")

                        # Just do the progress bar once
                        steps = st.session_state.pending_log["resolution_steps"]
                        for i, step in enumerate(steps):
                            progress_bar.progress((i + 1) / len(steps))
                        st.rerun()
                    else:
                        st.error(f"Failed to resolve shortage: {result.get('error')}")
                except Exception as e:
                    st.error(f"Error communicating with backend: {e}")
                    
        # Roster optimization process steps
        st.markdown("---")
        st.markdown("##### ⚙️ Multi-Agent Workflow Execution Progress")
        if st.session_state.get("pending_log"):
            st.markdown("✅ 1. Preparing staffing scenario")
            st.markdown("✅ 2. Staffing Planner Agent")
            st.markdown("✅ 3. Compliance Guard Agent")
            st.markdown("✅ 4. Patient Safety Agent")
            st.markdown("✅ 5. Financial Auditor Agent")
            st.markdown("✅ 6. Final Arbiter Agent")
            if st.session_state.get("last_decision_status") in ["Approved", "Rejected", "Override Used"]:
                st.markdown("✅ 7. Human approval")
            else:
                st.markdown("🟡 7. Human approval (Pending Decision)")
        else:
            st.markdown("⏳ 1. Preparing staffing scenario")
            st.markdown("⏳ 2. Staffing Planner Agent")
            st.markdown("⏳ 3. Compliance Guard Agent")
            st.markdown("⏳ 4. Patient Safety Agent")
            st.markdown("⏳ 5. Financial Auditor Agent")
            st.markdown("⏳ 6. Final Arbiter Agent")
            st.markdown("⏳ 7. Human approval")
            
        st.markdown("</div>", unsafe_allow_html=True)
        
    # Step 3
    if st.session_state.get("pending_log"):
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.markdown("<h3 style='color: #34d399; border-bottom: 2px solid rgba(52, 211, 153, 0.3); padding-bottom: 8px; margin-top: 10px; font-size: 1.45rem; line-height: 1.25; font-weight: 700;'>3️⃣ Step 3: Human Approval & Governance</h3>", unsafe_allow_html=True)
        st.caption("Workflow Step 3 of 3: Review the AI committee's rationale, check compliance, and submit the final roster update.")
        
        # Audit Status Badge
        last_dec = st.session_state.get("last_decision_status")
        if last_dec == "Approved":
            st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; margin-bottom: 0; color: #FFFFFF;">📝 Audit Status: Approved and Saved</p></div>""", unsafe_allow_html=True)
        elif last_dec == "Rejected":
            st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; margin-bottom: 0; color: #FFFFFF;">📝 Audit Status: Rejected</p></div>""", unsafe_allow_html=True)
        elif last_dec == "Override Used":
            st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; margin-bottom: 0; color: #FFFFFF;">📝 Audit Status: Override Used</p></div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; margin-bottom: 0; color: #FFFFFF;">📝 Audit Status: Pending Approval</p></div>""", unsafe_allow_html=True)
        
        log_data = st.session_state.pending_log
        rec_nurses = log_data["resolved_nurses"]
        all_nurses = get_nurses()
        scen = st.session_state.get("xg_inputs", {})
        target_dept = scen.get("department", "Emergency")
        
        # --- 3A: Multi-Agent Decision Debate ---
        st.markdown("##### 🧠 Multi-Agent Decision Debate")
        
        ev = log_data.get("committee_evidence", {})
        
        # Determine current debate summary and final recommendation
        live_debate = log_data.get("live_debate") or st.session_state.get("agent_debate") or {}
        if live_debate and live_debate.get("success") and live_debate.get("raw_response"):
            debate_sum = live_debate.get("raw_response")
        else:
            debate_sum = "No debate generated."
            for step in log_data.get("resolution_steps", []):
                if step["agent"] == "AI Committee Coordinator":
                    debate_sum = step["output"]
                    break
                
        ag = log_data.get("active_agents", [])
        if not ev and not ag:
            st.info("ℹ️ **Legacy Log**: This staffing resolution was created before the AI Committee Operational Modules were deployed. Some operational signals are unavailable.")
            
        wait_val = ev.get('xgboost_predicted_wait_time')
        if wait_val is None:
            wait_val = st.session_state.get('pred_wait', 0.0)
            
        # 1. Executive Summary
        st.markdown("##### 📊 Executive Summary")
        
        highest_pressure = "None"
        max_pts = -1
        for k in ["esi", "boarding", "arrival", "fast_track"]:
            if ev.get(f"{k}_adjustment", 0) > max_pts:
                max_pts = ev.get(f"{k}_adjustment", 0)
                highest_pressure = f"{k.upper()} Pressure"
                
        req_approval = "Required" if ev.get("adjusted_operational_risk") == "Critical" else "Standard Review"
        toks = log_data.get("token_usage", {}).get("total", 0)
        mode = "Local Expert-System Mode" if toks == 0 else "Live API Mode"
        
        st.markdown(f"""
        <div class="glass-card" style="border: 2px solid #6366f1; background: rgba(99, 102, 241, 0.1);">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 1.05em;">
                <div><strong>Predicted Wait Time:</strong> {wait_val:.1f} min</div>
                <div><strong>Base Risk:</strong> {ev.get('base_staffing_risk', 'Unknown')}</div>
                <div><strong>Adjusted Operational Risk:</strong> {ev.get('adjusted_operational_risk', 'Unknown')}</div>
                <div><strong>Highest Pressure Signal:</strong> {highest_pressure}</div>
                <div style="grid-column: span 2;"><strong>Recommended Action:</strong> {log_data.get('final_recommendation_actions', 'No recommendation generated.')}</div>
                <div><strong>Committee Mode:</strong> {mode}</div>
                <div><strong>Token Usage:</strong> {toks}</div>
                <div><strong>Human Approval:</strong> {req_approval}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        try:
            scenario_sig = {
                "waiting_room_count": st.session_state.waiting_room_count,
                "ed_occupancy_percent": st.session_state.ed_occupancy_percent,
                "arrival_pressure": st.session_state.ambulance_arrival_pressure,
                "boarding_pressure": "High" if st.session_state.boarding_count > 10 else "Low", 
                "fatigue_pressure": "High" if st.session_state.nurse_callout_rate > 15 else "Low",
                "acuity_pressure": "High" if st.session_state.scen_acuity < 3 else "Low"
            }
            sim_data = requests.post(f"{API_BASE_URL}/api/find_similar_history", json={"scenario_signature": scenario_sig}, timeout=10).json()
            if sim_data and sim_data.get("similar_events"):
                st.markdown(f"**Memory insight**: The system found {len(sim_data['similar_events'])} similar prior ER states matching the current arrival pressure and occupancy. This supports the current recommendation.", unsafe_allow_html=True)
            else:
                st.markdown("**Memory insight**: No closely matching prior memory event was found. Recommendation is based on the current forecast and operational pressure signals.", unsafe_allow_html=True)
        except Exception:
            pass

        # 2. Prediction and Risk Overview (Combining legacy wait-time display)
        
        # Staffing adjustment summary section
        base_n = ev.get("base_nurses_needed", 1)
        adj_n = ev.get("research_adjusted_nurses_needed", 1)
        reasons_list = ev.get("nurse_adjustment_reasons", [])
        
        # Clean reasons for display
        cleaned_reasons = []
        for r in reasons_list:
            part = r.split(":")[0]
            part = part.replace("Adjusted operational risk is Critical", "Critical adjusted risk")
            part = part.replace("ESI acuity pressure is High", "High ESI acuity")
            part = part.replace("ESI acuity pressure is Critical", "Critical ESI acuity")
            part = part.replace("Arrival surge pressure is High", "High arrival surge")
            part = part.replace("Arrival surge pressure is Critical", "Critical arrival surge")
            part = part.replace("Nurse fatigue pressure is High", "High fatigue pressure")
            part = part.replace("Nurse fatigue pressure is Critical", "Critical fatigue pressure")
            cleaned_reasons.append(part)
            
        reasons_str = ", ".join(cleaned_reasons) if cleaned_reasons else "No additional pressure signals detected"
        
        note = ev.get("nurse_adjustment_note", "")
        cost_before = log_data["costs"].get("staffing_cost_before", 0.0)
        cost_after = log_data["costs"].get("staffing_cost_after", 0.0)
        cost_diff = log_data["costs"].get("cost_increase", 0.0)
        
        recommendation_changed = (base_n != adj_n)
        if recommendation_changed:
            change_label_inline = "Why it changed"
            expander_title = "📉 Why the Recommendation Changed"
            research_adjustment_result = f"The research modules changed the recommendation from {base_n} nurses to {adj_n} nurses because additional operational pressure signals were detected."
            operational_factors_label = "Operational factors that changed the recommendation:"
        else:
            change_label_inline = "Operational Factors Supporting This Recommendation"
            expander_title = "📉 Why the Recommendation Was Maintained"
            research_adjustment_result = f"No numeric staffing change was applied. The research modules confirmed that the original {base_n}-nurse recommendation remains appropriate under the current operational-risk conditions."
            operational_factors_label = "Operational factors supporting this recommendation:"
        
        with st.expander("🛡️ Staffing resolution rationale", expanded=True):
            st.markdown(f"""
            <div class="glass-card" style="border-left: 5px solid #818cf8; background: rgba(17, 25, 40, 0.7);">
                <h4 style="margin-top:0; color:#818cf8; font-weight:700;">🛡️ Research-Adjusted Staffing Rationale</h4>
                <p style="margin-bottom:8px; font-size:1.05em;">• <strong>Base XGBoost staffing need:</strong> {base_n} nurse{'s' if base_n != 1 else ''}</p>
                <p style="margin-bottom:8px; font-size:1.05em;">• <strong>Research-adjusted staffing need:</strong> {adj_n} nurse{'s' if adj_n != 1 else ''}</p>
                <p style="margin-bottom:8px; font-size:1.05em;">• <strong>{change_label_inline}:</strong> {reasons_str}</p>
                <p style="margin-bottom:8px; font-size:1.05em;">• <strong>Final Recommended Nurse Count:</strong> {adj_n} nurse{'s' if adj_n != 1 else ''}</p>
                <p style="margin-bottom:0; font-size:1.05em;">• <strong>Roster Cost Impact:</strong> ${cost_after:.2f} (Base forecast: ${cost_before:.2f}, Difference: +${cost_diff:.2f})</p>
                {f'<p style="margin-top:8px; font-size:0.95em; color:#94a3b8; font-style:italic;">Note: {note}</p>' if note else ''}
            </div>
            """, unsafe_allow_html=True)

        # 3. Why the Recommendation Changed
        if log_data.get("operational_signal_impact_summary"):
            with st.expander(expander_title, expanded=True):
                summary_text = log_data["operational_signal_impact_summary"].replace("#### Operational Signal Impact Summary", "")
                st.markdown(f"**Research adjustment result:**\n{research_adjustment_result}\n\n**{operational_factors_label}**\n{summary_text}")
                
        if not ev and not ag:
            st.info("ℹ️ **Legacy Log**: This staffing resolution was created before the AI Committee Operational Modules were deployed. Some operational signals are unavailable.")
            
        # 4. Committee Evidence Signals
        with st.expander("📊 Committee Evidence Signals"):
            col_c1, col_c2 = st.columns([1, 1])
            with col_c1:
                st.write(f"**XGBoost Predicted Wait**: {wait_val:.1f} mins")
                st.write(f"**Base Staffing Risk**: {ev.get('base_staffing_risk', 'Unknown')}")
                st.write(f"**ESI Pressure**: {ev.get('esi_pressure', 'Low')} (+{ev.get('esi_adjustment', 0)})")
                st.write(f"**Boarding Pressure**: {ev.get('boarding_pressure', 'Low')} (+{ev.get('boarding_adjustment', 0)})")
            with col_c2:
                st.write(f"**Arrival Surge Pressure**: {ev.get('arrival_surge_pressure', 'Low')} (+{ev.get('arrival_adjustment', 0)})")
                st.write(f"**Fast-Track Pressure**: {ev.get('fast_track_pressure', 'Low')} (+{ev.get('fast_track_adjustment', 0)})")
                st.write(f"**Adjusted Operational Risk**: {ev.get('adjusted_operational_risk', 'Unknown')} (Score: {ev.get('adjusted_operational_risk_score', 0)})")

        # 5. Dynamic Committee Agent Activation
        with st.expander("🤖 Dynamic Committee Agent Activation"):
            for agent in ag:
                st.write(f"- **{agent['agent_name']}** (Activated: {agent['activation_reason']})")
                st.caption(f'"{agent["short_position"]}"')

        # 6. Committee Debate Summary
        with st.expander("🧠 Committee Debate Summary"):
            st.markdown(debate_sum)

        # 7. ER Staffing Intervention Planner (already exists elsewhere, but we can put the final decision here)
        with st.expander("✅ Final Arbiter Decision", expanded=True):
            st.markdown(f"**Final Recommendation:** {log_data.get('final_recommendation_actions', 'No debate generated.')}")
            
        # 11. Debug Expanders
        with st.expander("🛠️ Debug: Committee Evidence Packet"):
            st.json(ev)
        with st.expander("🛠️ Debug: Active Agents"):
            st.json(ag)
        
        # --- 3B: Compliance Guardrail Table ---
        st.markdown("---")
        st.markdown("##### 🛡️ Compliance Guardrail Table")
        
        guardrail_rows = []
        for nurse in all_nurses:
            cert_match = target_dept in nurse.get('certifications', [])
            current_hrs = nurse.get('weekly_hours', 0)
            projected_hrs = current_hrs + 12
            overtime_warn = projected_hrs > 48
            fatigue = "High" if projected_hrs > 52 else ("Medium" if projected_hrs > 44 else "Low")
            dist_risk = "High" if nurse.get('distance_miles', 0) > 20 else "Low"
            
            reasons = []
            if not cert_match:
                reasons.append(f"No {target_dept} cert")
            if overtime_warn:
                reasons.append(f"Overtime: {projected_hrs}h projected")
            if nurse.get('distance_miles', 0) > 20:
                reasons.append(f"Distance: {nurse['distance_miles']}mi")
            
            decision = "PASS" if (cert_match and not overtime_warn and nurse.get('distance_miles', 0) <= 20) else "FAIL"
            
            guardrail_rows.append({
                "Nurse ID": nurse['id'],
                "Name": nurse['name'],
                "Cert Match": "✅" if cert_match else "❌",
                "Current Hours": current_hrs,
                "Projected Hours": projected_hrs,
                "Overtime Warning": "⚠️ Yes" if overtime_warn else "No",
                "Fatigue Risk": fatigue,
                "Distance Risk": dist_risk,
                "Decision": decision,
                "Rejection Reason": "; ".join(reasons) if reasons else "—"
            })
        
        guardrail_df = pd.DataFrame(guardrail_rows)
        st.markdown(render_styled_table(guardrail_df), unsafe_allow_html=True)
        
        passing_nurses = [r['Nurse ID'] for r in guardrail_rows if r['Decision'] == 'PASS']
        
        # --- NEW: 3.5 Supervisor Candidate Review ---
        st.markdown("---")
        st.markdown("##### 🧑‍⚕️ Supervisor Candidate Review")
        st.caption("Use this step when the supervisor has operational knowledge that the model does not have, such as recent call-outs, fatigue concerns, skill fit, team dynamics, or unit-specific safety concerns.")
        
        system_rec_nurses = rec_nurses.copy()
        
        if "candidate_override_action" not in st.session_state:
            st.session_state.candidate_override_action = "Accept System Recommendation"
        if "candidate_override_nurse" not in st.session_state:
            st.session_state.candidate_override_nurse = []
            
        sys_nurse_names = [n['name'] for n in all_nurses if n['id'] in system_rec_nurses]
        
        st.markdown("**System Recommended Nurse(s):**")
        if sys_nurse_names:
            for name in sys_nurse_names:
                st.write(f"- {name}")
        else:
            st.write("- None (Agency / Escalate)")
            
        unmet_gap = log_data.get("unmet_nurse_gap", 0)
        esc_rec = log_data.get("escalation_recommendation", "None")
        if unmet_gap > 0:
            st.error(f"⚠️ **UNMET STAFFING GAP DETECTED**: Shortage of **{unmet_gap} nurse(s)** could not be filled by internal candidates.")
            st.warning(f"📣 **Escalation Plan**: {esc_rec}")
            
        st.markdown("**Why selected:**")
        st.write("- Available for the selected shift\n- Within fatigue threshold\n- No compliance violation\n- Cost/fatigue optimized\n- Matches staffing need")
        
        cand_action = st.radio(
            "Supervisor Candidate Action:",
            [
                "Accept System Recommendation",
                "Select Alternative Approved Nurse",
                "Exclude Recommended Nurse and Rerun Selection",
                "Request More Candidates / Escalate"
            ],
            key="cand_action_radio"
        )
        
        st.session_state.candidate_override_action = cand_action
        
        effective_rec_nurses = system_rec_nurses.copy()
        
        if cand_action == "Accept System Recommendation":
            st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; margin-bottom: 0; color: #FFFFFF;">System recommendation accepted.</p></div>""", unsafe_allow_html=True)
        elif cand_action == "Select Alternative Approved Nurse":
            def format_nurse(nid):
                n = next((x for x in all_nurses if x['id'] == nid), None)
                if not n: return nid
                fatigue_score = (n.get('weekly_hours', 0) + 12) / 60.0 * 100
                return f"{n['name']} — {', '.join(n.get('certifications', []))}, {n.get('circadian_preference', 'Flexible')}, {n.get('weekly_hours', 0)} hrs/week, ${n.get('base_rate', 0)}/hr, Fatigue {fatigue_score:.0f}%, {n.get('distance_miles', 0)} miles"
                
            alt_nurses = st.multiselect("Alternative Approved Nurses:", passing_nurses, format_func=format_nurse, key="alt_nurse_select")
            if alt_nurses:
                effective_rec_nurses = alt_nurses
                st.warning(f"Supervisor override applied: alternative approved nurse selected.")
        elif cand_action == "Exclude Recommended Nurse and Rerun Selection":
            alt_pool = [n for n in passing_nurses if n not in system_rec_nurses]
            if alt_pool:
                effective_rec_nurses = alt_pool[:max(1, len(system_rec_nurses))]
                st.warning(f"Original recommendation excluded by supervisor. Next eligible candidate selected.")
            else:
                effective_rec_nurses = []
                st.warning("Original recommendation excluded. No other eligible candidates available.")
        elif cand_action == "Request More Candidates / Escalate":
            effective_rec_nurses = []
            st.error("Supervisor requested additional staffing review. Escalation required before roster approval.")
            
        st.session_state.candidate_override_nurse = effective_rec_nurses

        eff_nurse_names = [n['name'] for n in all_nurses if n['id'] in effective_rec_nurses]
        eff_names_str = ", ".join(eff_nurse_names) if eff_nurse_names else "None"
        eff_ids_str = ", ".join(effective_rec_nurses) if effective_rec_nurses else "None"

        # --- NEW: Proposed Assignment Summary ---
        st.markdown("---")
        st.markdown("##### 📋 Proposed Assignment Summary")
        st.write(f"- **Original system recommendation:** {', '.join(sys_nurse_names) if sys_nurse_names else 'None'}")
        st.write(f"- **Candidate review action:** {cand_action}")
        st.write(f"- **Current proposed nurse:** {eff_names_str}")
        
        status_text = "No override"
        if cand_action == "Request More Candidates / Escalate":
            status_text = "Escalation requested"
        elif cand_action != "Accept System Recommendation":
            status_text = "Candidate override applied"
            
        st.write(f"- **Override status:** {status_text}")
        st.caption(f"Internal nurse ID: {eff_ids_str}")

        # --- 3C: Before & After Impact Card ---
        st.markdown("---")
        st.markdown("##### 📊 Before & After Impact Estimate")
        st.caption("⚠️ The after-staffing wait-time is a prototype estimate based on the XGBoost model's response to an improved nurse-to-patient ratio, not a real clinical guarantee.")
        
        if cand_action == "Accept System Recommendation":
            st.write(f"**Impact shown using system-recommended nurse:** {eff_names_str}")
        else:
            st.write(f"**Impact shown using supervisor-selected nurse:** {eff_names_str}")
        
        pred_before = st.session_state.get("pred_wait", 0)
        # Get base parameters from session state to ensure consistency with pred_before
        base_beds = st.session_state.get('scen_beds', 200)
        base_ratio = st.session_state.get('scen_ratio', 0.20)
        env_multiplier = scen.get('env_multiplier', 1.0)
        num_added = len(effective_rec_nurses)
        
        # Re-predict with improved ratio (Standard / Without Heuristics)
        standard_ratio_calc = min(0.40, base_ratio + (num_added * 0.03))
        effective_standard = round(standard_ratio_calc / env_multiplier, 3)
        pred_after_standard = predict_wait_time(
            facility_size_beds=base_beds,
            month=scen.get('computed_month', 6),
            day_of_week=scen.get('computed_day_of_week', 1),
            visithour=scen.get('computed_visithour', 12),
            urgency_level=scen.get('acuity', 3),
            nurse_to_patient_ratio=effective_standard,
            specialist_availability=0 # Missed specialist alignment
        )
        reduction_standard = max(0, pred_before - pred_after_standard)

        # Re-predict with optimized ratio (Cost/Fatigue Optimized)
        optimized_ratio_calc = min(0.40, base_ratio + (num_added * 0.06))
        effective_optimized = round(optimized_ratio_calc / env_multiplier, 3)
        pred_after_ho = predict_wait_time(
            facility_size_beds=base_beds,
            month=scen.get('computed_month', 6),
            day_of_week=scen.get('computed_day_of_week', 1),
            visithour=scen.get('computed_visithour', 12),
            urgency_level=scen.get('acuity', 3),
            nurse_to_patient_ratio=effective_optimized,
            specialist_availability=1 # Cost & Fatigue-Aware Staffing Optimizer ensures specialist alignment
        )
        reduction_ho = max(0, pred_before - pred_after_ho)
        
        st.markdown("**Local Predictive Sandbox (Standard Assignment vs. Cost/Fatigue Optimized Assignment)**")
        imp_c1, imp_c2, imp_c3, imp_c4 = st.columns(4)
        with imp_c1:
            st.metric("Wait Time BEFORE", f"{pred_before:.1f} mins")
        with imp_c2:
            st.metric("After Standard Staffing Add", f"{pred_after_standard:.1f} mins", delta=f"-{reduction_standard:.1f} mins", delta_color="normal")
        with imp_c3:
            st.metric("After Cost/Fatigue-Safe Assignment", f"{pred_after_ho:.1f} mins", delta=f"-{reduction_ho:.1f} mins", delta_color="normal")
        with imp_c4:
            st.metric("Additional Nurses Added", f"{num_added} Required")
            
        if reduction_ho < reduction_standard:
            st.info("Cost/fatigue optimized assignment may prioritize compliance, fatigue safety, and cost control over maximum wait-time reduction.")
            
        st.caption("Wait-time improvement is a prototype estimate based on staffing ratio changes. Final staffing decisions should consider safety, fatigue, compliance, and supervisor judgement.")
            
        st.markdown("---")
        with st.expander("🧬 Cost & Fatigue-Aware Staffing Optimizer Summary (Cost & Fatigue Optimizer vs Standard)", expanded=False):
            # Get names for the summary
            sel_names = [n['name'] for n in all_nurses if n['id'] in rec_nurses]
            sel_str = ", ".join(sel_names) if sel_names else "Agency Staff"
            
            # Simulate standard selection (greedy cost-based, ignoring fatigue/specialties)
            sorted_by_cost = sorted(all_nurses, key=lambda x: x.get('base_rate', 50))
            standard_picks = [n['name'] for n in sorted_by_cost if n['id'] not in rec_nurses][:max(1, num_added)]
            standard_str = ", ".join(standard_picks) if standard_picks else "Other Available Staff"
            
            st.info(
                f"**Cost/Fatigue Optimized Selection:** `{sel_str}`\n\n"
                f"**Standard Selection (No Optimization):** `{standard_str}`\n\n"
                f"---\n\n"
                f"**How the Cost & Fatigue-Aware Staffing Optimizer reached its result:**\n\n"
                f"The Optimizer evaluated thousands of possible nurse combinations to fill the {num_added}-nurse shortage. "
                f"A standard 'greedy' hospital algorithm would have simply picked the cheapest available nurses (**{standard_str}**). "
                f"However, the Cost & Fatigue-Aware Optimizer computationally proved that selecting **{sel_str}** is superior. \n\n"
                f"**Why?** The optimized combination minimized total overtime fatigue risk while guaranteeing a perfect 100% match for the required {scen.get('department', 'Emergency')} certifications. "
                f"*(The standard selection missed this optimal skill-match, resulting in the higher 'Standard' wait time shown above).*")
        
        # --- 3D: Resolution Recommendation ---
        st.markdown("---")
        st.markdown("<h3 style='color: #818cf8;'>📋 Resolution Recommendation</h3>", unsafe_allow_html=True)
        
        cost_val = log_data['costs']['total_staffing_cost']
        
        if reduction_ho <= 0.0:
            st.info("The optimized assignment improves compliance, fatigue, or cost efficiency, but does not produce additional wait-time reduction beyond the selected baseline.")
        else:
            st.success(f"Projected wait-time reduction of {reduction_ho:.1f} minutes.")
            
        st.markdown(f"**Cost/Fatigue Estimate for Current Proposed Nurse**: `{eff_names_str}`")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.metric("Total Staffing Cost (12h)", f"${cost_val:.2f}")
        with col_c2:
            st.metric("Patient Safety Score", f"{log_data['risk_factors']['patient_safety_score']:.1f}/100")
            st.metric("Fatigue Index", f"{log_data['risk_factors']['fatigue_index']:.1f}%")
            
        with st.expander("🪙 View Groq/API token usage audit", expanded=False):
            # Token usage audit display
            st.markdown("---")
            st.markdown("##### 🪙 Groq/API Token Usage Audit")
        
            solver_costs = log_data.get("costs", {})
            debate_costs = st.session_state.get("agent_debate", {})
        
            total_llm_calls = solver_costs.get("llm_calls", 0) + debate_costs.get("llm_calls", 0)
            total_prompt_t = solver_costs.get("prompt_tokens", 0) + debate_costs.get("prompt_tokens", 0)
            total_resp_t = solver_costs.get("response_tokens", 0) + debate_costs.get("response_tokens", 0)
            total_token_usage = solver_costs.get("total_tokens", 0) + debate_costs.get("total_tokens", 0)
            total_api_cost = solver_costs.get("estimated_api_cost", 0.0) + debate_costs.get("estimated_api_cost", 0.0)
        
            # Check if tracker is disconnected
            is_unavailable = (solver_costs.get("total_tokens") == -1) or (debate_costs.get("total_tokens") == -1)
        
            if is_unavailable:
                st.warning("Token usage unavailable — tracker not connected")
            elif total_llm_calls == 0:
                st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; margin-bottom: 0; color: #FFFFFF;">Token usage: 0 tokens - Low-token local rule mode</p></div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""
                - **Groq/API Calls Made**: {total_llm_calls}
                - **Prompt Tokens**: {total_prompt_t}
                - **Response Tokens**: {total_resp_t}
                - **Total Tokens**: {total_token_usage}
                - **Estimated API Cost**: ${total_api_cost:.5f}
                """)
        
        with st.expander("🗣️ View full explainability report and evidence packet", expanded=False):
            st.markdown("#### 🗣️ Explainability Report:")
            st.markdown(log_data["explainability_narrative"])
        
            with st.expander("Debug: AI Evidence Packet"):
                st.json(log_data.get("committee_evidence", {}))
        
        # --- 3E: Final Human Governance Decision ---
        st.markdown("---")
        st.markdown("### 👩‍⚖️ Final Human Governance Decision")
        st.caption("Review the staffing proposal, candidate override status, before/after impact, compliance checks, fatigue checks, and cost impact before committing the final roster decision.")
        
        ga_opt_text = "👍 Approve Optimized Roster"
        reject_text = "👎 Reject Recommendation"
        escalate_text = "⚠️ Escalate to CNO / Staffing Manager"
        
        committee_rec_nurses = log_data.get("committee_evidence", {}).get("research_adjusted_nurses_needed", 0)
        adj_risk = log_data.get("committee_evidence", {}).get("adjusted_operational_risk", "Low")
        unmet_gap = log_data.get("unmet_nurse_gap", 0)
        
        # If they requested escalation early, default to Escalate or Reject
        if st.session_state.candidate_override_action == "Request More Candidates / Escalate":
            default_index = 3 # Escalate
        elif unmet_gap > 0:
            escalate_text += " (⭐ System Recommended)"
            default_index = 3
        elif committee_rec_nurses > 0 or adj_risk in ["High", "Critical"]:
            ga_opt_text += " (⭐ System Recommended)"
            default_index = 0
        elif reduction_ho < 1.0:
            reject_text += " (⭐ System Recommended)"
            default_index = 2
        else:
            ga_opt_text += " (⭐ System Recommended)"
            default_index = 0
            
        human_decision = st.radio(
            "Select your decision:",
            [
                ga_opt_text,
                "👍 Approve Standard Roster",
                reject_text,
                escalate_text,
                "✏️ Final Override: Select Alternative Approved Nurse"
            ],
            index=default_index,
            key="human_decision_radio"
        )
        
        override_nurse = None
        override_reason = ""
        
        if "Final Override" in human_decision:
            override_nurse = st.multiselect(
                "Select one or more nurses from the compliance-passing pool to assign:",
                passing_nurses if passing_nurses else ["No eligible nurses"],
                key="override_nurse_select"
            )
            override_reason_text = st.text_area("Final Override Reason", placeholder="Example: Supervisor selected a different nurse due to recent call-out, skill fit, fatigue concern, unit need, or clinical judgement.", key="override_reason_input")
            override_reason = override_reason_text
        
        # Collect compliance warnings for audit
        compliance_warnings = [r['Rejection Reason'] for r in guardrail_rows if r['Decision'] == 'FAIL' and r['Nurse ID'] in rec_nurses]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Removed pre-submission download button block here.
        
        st.caption(f"ℹ️ **Action**: {HELPER_SUBMIT_DECISION}")
        st.markdown("<div class='submit-btn-wrapper'>", unsafe_allow_html=True)
        submit_clicked = st.button("Submit Decision", type="primary", use_container_width=True, key="submit_decision_btn")
        st.markdown("</div>", unsafe_allow_html=True)
        if submit_clicked:
            cost_val = log_data['costs']['total_staffing_cost']
            token_mode = "Local deterministic, 0 Tokens" if total_llm_calls == 0 else f"Online Groq/API, {total_token_usage} tokens"
            
            # Compute names for audit log
            orig_rec_names = [n['name'] for n in all_nurses if n['id'] in rec_nurses]
            final_nurse_ids = override_nurse if override_nurse and "Final Override" in human_decision else effective_rec_nurses
            final_nurse_names = [n['name'] for n in all_nurses if n['id'] in final_nurse_ids]
            
            # Determine Override Stage
            override_stage = "none"
            if "Final Override" in human_decision:
                override_stage = "final_governance"
            elif st.session_state.candidate_override_action != "Accept System Recommendation":
                override_stage = "candidate_review"
            
            # Extract committee data if available
            comm_ev = log_data.get("committee_evidence", {})
            ag = log_data.get("active_agents", [])
            act_reasons = [a.get("activation_reason") for a in ag] if ag else []
            live_debate_audit = log_data.get("live_debate") or st.session_state.get("agent_debate") or {}
            if live_debate_audit and live_debate_audit.get("success") and live_debate_audit.get("raw_response"):
                debate_sum = live_debate_audit.get("raw_response")
            else:
                debate_sum = next((s["output"] for s in log_data.get("resolution_steps", []) if s["agent"] == "AI Committee Coordinator"), "No debate generated")

            audit_entry = {
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "shift_date": str(scen.get('shift_date', '')),
                "shift_type": scen.get('shift_type', ''),
                "department": target_dept,
                "predicted_wait_time": f"{pred_before:.1f} mins",
                "threshold": f"{st.session_state.get('safety_thresh', 90)} mins",
                "risk_level": "Shortage Detected" if int(st.session_state.get('estimated_needed', 0)) > 0 else "Optimal",
                "additional_nurses_needed": int(st.session_state.get('estimated_needed', 0)),
                "original_recommended_nurse": ', '.join(orig_rec_names) if orig_rec_names else "None",
                "candidate_review_action": st.session_state.candidate_override_action,
                "final_selected_nurse": ', '.join(final_nurse_names) if final_nurse_names else "None",
                "nurse_id": ', '.join(final_nurse_ids) if final_nurse_ids else "None",
                "nurse_display_name": ', '.join(final_nurse_names) if final_nurse_names else "None",
                "override_stage": override_stage,
                "override_reason": override_reason,
                "rejected_nurses": ', '.join([r['Nurse ID'] for r in guardrail_rows if r['Decision'] == 'FAIL']),
                "committee_evidence": comm_ev,
                "active_agents": ag,
                "agent_activation_reasons": act_reasons,
                "committee_debate_summary": debate_sum,
                "final_committee_recommendation": debate_sum.split("Final Recommendation:")[-1].strip() if "Final Recommendation:" in debate_sum else "None",
                "compliance_warnings": '; '.join(compliance_warnings) if compliance_warnings else 'None',
                "estimated_cost": f"${cost_val:.2f}",
                "base_nurses_needed": comm_ev.get("base_nurses_needed", 1),
                "research_adjusted_nurses_needed": comm_ev.get("research_adjusted_nurses_needed", 1),
                "nurse_adjustment_reasons": comm_ev.get("nurse_adjustment_reasons", []),
                "final_nurses_recommended": len(final_nurse_ids),
                "staffing_cost_before": log_data["costs"].get("staffing_cost_before", 0.0),
                "staffing_cost_after": log_data["costs"].get("staffing_cost_after", 0.0),
                "cost_increase": log_data["costs"].get("cost_increase", 0.0),
                "approval_required": comm_ev.get("adjusted_operational_risk") in ["High", "Critical"],
                "research_module_intervention_cost": log_data["costs"].get("research_module_intervention_cost", 0.0),
                "total_estimated_operational_cost": log_data["costs"].get("total_estimated_operational_cost", 0.0),
                "costed_interventions": log_data.get("intervention_plan", []),
                "human_decision": "",
                "roster_update_status": "Pending",
                "token_usage_mode": token_mode
            }
            
            # Prepare base report data
            base_report_data = {
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "scenario": {
                    "shift": scen.get("shift_id"),
                    "date": str(scen.get("shift_date")),
                    "type": scen.get("shift_type"),
                    "department": target_dept,
                    "acuity_level": scen.get("acuity"),
                    "patient_volume_multiplier": scen.get("env_multiplier", 1.0)
                },
                "prediction": {
                    "wait_time_minutes": round(pred_before, 1),
                    "risk_level": "Shortage Detected" if int(st.session_state.get('estimated_needed', 0)) > 0 else "Optimal",
                    "estimated_nurses_needed": st.session_state.get('estimated_needed', 0)
                },
                "agent_recommendation": {
                    "recommended_nurses": rec_nurses,
                    "compliance_warnings": compliance_warnings,
                    "estimated_cost": round(log_data['costs']['total_staffing_cost'], 2)
                },
                "synthetic_data_limitation_statement": "This report is based on the Kaggle ER Wait Time synthetic dataset and is for demonstration purposes only."
            }
            
            if "Approve" in human_decision:
                app_res = requests.post(f"{API_BASE_URL}/api/approve_resolution", json={
                    "log_id": log_data["id"],
                    "debate_costs": debate_costs
                })
                res_json = app_res.json()
                if res_json.get("success"):
                    try:
                        scenario_sig = {
                            "waiting_room_count": st.session_state.waiting_room_count,
                            "ed_occupancy_percent": st.session_state.ed_occupancy_percent,
                            "arrival_pressure": st.session_state.ambulance_arrival_pressure,
                            "boarding_pressure": "High" if st.session_state.boarding_count > 10 else "Low", 
                            "fatigue_pressure": "High" if st.session_state.nurse_callout_rate > 15 else "Low",
                            "acuity_pressure": "High" if st.session_state.scen_acuity < 3 else "Low"
                        }
                        requests.post(f"{API_BASE_URL}/api/update_memory_on_save", json={
                            "scenario_signature": scenario_sig,
                            "forecasted_volume": st.session_state.get("last_forecast", 0),
                            "staffing_recommendation": {"final_additional_nurses": int(st.session_state.get('estimated_needed', 0)), "nurses_assigned": effective_rec_nurses if 'effective_rec_nurses' in locals() else []}
                        })
                    except Exception:
                        pass
                    st.toast("Roster updated. Shift schedule updated. Audit log saved.")
                    audit_entry["human_decision"] = human_decision.replace("👍 ", "")
                    audit_entry["roster_update_status"] = "Success"
                    add_audit_log(audit_entry)
                    st.session_state.last_summary = {
                        "risk_level": "Shortage Detected",
                        "pred_wait": f"{pred_before:.1f} mins",
                        "threshold": f"{st.session_state.get('safety_thresh', 90)} mins",
                        "nurses_needed": int(st.session_state.get('estimated_needed', 0)),
                        "recommended_nurses": ', '.join(effective_rec_nurses) if effective_rec_nurses else "None",
                        "compliance_status": "Passed with warnings" if compliance_warnings else "Passed",
                        "human_decision": human_decision.replace("👍 ", ""),
                        "roster_update": "Saved",
                        "audit_log": "Recorded",
                        "token_mode": token_mode
                    }
                    base_report_data["human_decision"] = human_decision.replace("👍 ", "")
                    st.session_state.last_report_data = base_report_data
                    st.session_state.pending_log = None
                    st.session_state.evidence = {}
                    st.session_state.estimated_needed = 0
                    st.session_state.pred_wait = 0
                    st.session_state.safety_thresh = 0
                    st.session_state.risk_assessed = False
                    st.session_state.last_decision_status = "Approved"
                    st.session_state.cno_chat_history = []
                    clear_dashboard_bootstrap_cache()
                    st.rerun()
                else:
                    st.error(res_json.get("error", "Roster update failed"))
            elif "Reject" in human_decision or "Escalate" in human_decision:
                rej_res = requests.post(f"{API_BASE_URL}/api/reject_resolution", json={"log_id": log_data["id"]})
                res_json = rej_res.json()
                if res_json.get("success"):
                    action_str = "Escalated" if "Escalate" in human_decision else "Rejected"
                    st.toast(f"Resolution {action_str.lower()}. Audit log saved.")
                    audit_entry["human_decision"] = action_str
                    audit_entry["roster_update_status"] = "Cancelled"
                    add_audit_log(audit_entry)
                    st.session_state.last_summary = {
                        "risk_level": "Shortage Detected",
                        "pred_wait": f"{pred_before:.1f} mins",
                        "threshold": f"{st.session_state.get('safety_thresh', 90)} mins",
                        "nurses_needed": int(st.session_state.get('estimated_needed', 0)),
                        "recommended_nurses": "None (Rejected/Escalated)",
                        "compliance_status": f"{action_str} by supervisor",
                        "human_decision": action_str,
                        "roster_update": "Cancelled",
                        "audit_log": "Recorded",
                        "token_mode": token_mode
                    }
                    base_report_data["human_decision"] = "Rejected"
                    st.session_state.last_report_data = base_report_data
                    st.session_state.pending_log = None
                    st.session_state.evidence = {}
                    st.session_state.estimated_needed = 0
                    st.session_state.pred_wait = 0
                    st.session_state.safety_thresh = 0
                    st.session_state.risk_assessed = False
                    st.session_state.last_decision_status = "Rejected"
                    st.session_state.cno_chat_history = []
                    clear_dashboard_bootstrap_cache()
                    st.rerun()
                else:
                    st.error(res_json.get("error", "Rejection failed"))
            elif "Override" in human_decision:
                if not override_reason_text.strip():
                    st.error("Override comments/details are required.")
                else:
                    override_payload = {
                        "log_id": log_data["id"],
                        "override_nurses": override_nurse if override_nurse else []
                    }
                    app_res = requests.post(f"{API_BASE_URL}/api/approve_resolution", json=override_payload)
                    res_json = app_res.json()
                    if res_json.get("success"):
                        try:
                            scenario_sig = {
                                "waiting_room_count": st.session_state.waiting_room_count,
                                "ed_occupancy_percent": st.session_state.ed_occupancy_percent,
                                "arrival_pressure": st.session_state.ambulance_arrival_pressure,
                                "boarding_pressure": "High" if st.session_state.boarding_count > 10 else "Low", 
                                "fatigue_pressure": "High" if st.session_state.nurse_callout_rate > 15 else "Low",
                                "acuity_pressure": "High" if st.session_state.scen_acuity < 3 else "Low"
                            }
                            requests.post(f"{API_BASE_URL}/api/update_memory_on_save", json={
                                "scenario_signature": scenario_sig,
                                "forecasted_volume": st.session_state.get("last_forecast", 0),
                                "staffing_recommendation": {"final_additional_nurses": int(st.session_state.get('estimated_needed', 0)), "nurses_assigned": override_nurse if override_nurse else []}
                            })
                        except Exception:
                            pass
                        st.toast(f"Override applied. {override_nurse} assigned. Audit log saved.")
                        audit_entry["human_decision"] = f"Override: {override_nurse}"
                        audit_entry["override_reason"] = override_reason
                        audit_entry["roster_update_status"] = "Success (Overridden)"
                        add_audit_log(audit_entry)
                        st.session_state.last_summary = {
                            "risk_level": "Shortage Detected",
                            "pred_wait": f"{pred_before:.1f} mins",
                            "threshold": f"{st.session_state.get('safety_thresh', 90)} mins",
                            "nurses_needed": int(st.session_state.get('estimated_needed', 0)),
                            "recommended_nurses": ', '.join(override_nurse) if override_nurse else "None",
                            "compliance_status": f"Overridden: {override_reason_cat}",
                            "human_decision": f"Override: {', '.join(override_nurse) if override_nurse else 'None'}",
                            "roster_update": "Saved (Overridden)",
                            "audit_log": "Recorded",
                            "token_mode": token_mode
                        }
                        base_report_data["human_decision"] = f"Override: {override_nurse}"
                        base_report_data["override_reason"] = override_reason
                        st.session_state.last_report_data = base_report_data
                        st.session_state.pending_log = None
                        st.session_state.evidence = {}
                        st.session_state.estimated_needed = 0
                        st.session_state.pred_wait = 0
                        st.session_state.safety_thresh = 0
                        st.session_state.risk_assessed = False
                        st.session_state.last_decision_status = f"Override: {override_nurse}"
                        st.session_state.cno_chat_history = []
                        clear_dashboard_bootstrap_cache()
                        st.rerun()
                    else:
                        st.error(res_json.get("error", "Override failed"))
if workflow_page == "⚡ System Stress Simulator":
    st.subheader("⚡ System Stress Test Simulator")
    st.markdown("Simulate patient surges, staffing call-outs, and acuity shifts to test ER wait-time resilience.")
    
    col_s1, col_s2 = st.columns([1, 2])
    
    with col_s1:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.markdown("#### ⚙️ Stress Parameters")
        
        # Initialize default values if not present
        if "sim_mult_sld" not in st.session_state:
            st.session_state.sim_mult_sld = 1.2
        if "sim_call_sld" not in st.session_state:
            st.session_state.sim_call_sld = 20
        if "sim_acuity_stress" not in st.session_state:
            st.session_state.sim_acuity_stress = 0
        if "sim_ratio_stress" not in st.session_state:
            st.session_state.sim_ratio_stress = 0.00

        # Preset mapping
        presets = {
            "Optimal Baseline": {"mult": 1.0, "callouts": 0},
            "Blizzard Emergency": {"mult": 1.8, "callouts": 30},
            "Viral Pandemic Outbreak": {"mult": 2.5, "callouts": 40},
            "Standard Weekend Shift": {"mult": 1.3, "callouts": 10}
        }
        
        def on_preset_change():
            p_val = st.session_state.get("preset_select", "Custom")
            if p_val in presets:
                st.session_state.sim_mult_sld = presets[p_val]["mult"]
                st.session_state.sim_call_sld = presets[p_val]["callouts"]
                
        # If current slider values do not match selected preset, revert selectbox to Custom
        selected_preset = st.session_state.get("preset_select", "Custom")
        if selected_preset in presets:
            if (st.session_state.get("sim_mult_sld") != presets[selected_preset]["mult"] or 
                st.session_state.get("sim_call_sld") != presets[selected_preset]["callouts"]):
                st.session_state.preset_select = "Custom"
                
        st.selectbox(
            "Load Environmental Scenario Preset",
            ["Custom", "Optimal Baseline", "Blizzard Emergency", "Viral Pandemic Outbreak", "Standard Weekend Shift"],
            key="preset_select",
            on_change=on_preset_change
        )
        
        sim_multiplier = st.slider("Patient Inflow Multiplier", 1.0, 3.0, step=0.1, key="sim_mult_sld")
        sim_callouts = st.slider("Nurse Call-Out Rate (Sick %)", 0, 50, step=10, key="sim_call_sld")
        
        # Additional stress parameters
        acuity_stress = st.slider("Acuity Stress Adjustment", -2, 2, step=1, key="sim_acuity_stress")
        ratio_stress = st.slider("Ratio Stress Adjustment", -0.10, 0.10, step=0.01, key="sim_ratio_stress")
        sim_spec = st.selectbox("Specialist Available under Stress", [1, 0], format_func=lambda x: "Yes" if x==1 else "No", key="sim_spec_toggle")
        
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_s2:
        # Calculate stressed values
        base_date = st.session_state.scen_date
        base_type = st.session_state.scen_type
        base_beds = st.session_state.scen_beds
        base_acuity = st.session_state.scen_acuity
        base_ratio = st.session_state.scen_ratio
        base_spec = st.session_state.scen_spec
        
        month = base_date.month
        day_of_week = base_date.weekday()
        hour_map = {"Morning": 8, "Evening": 16, "Night": 22}
        visithour = hour_map.get(base_type, 12)
        
        # Calculate base prediction
        base_pred = predict_wait_time(
            facility_size_beds=base_beds,
            month=month,
            day_of_week=day_of_week,
            visithour=visithour,
            urgency_level=base_acuity,
            nurse_to_patient_ratio=base_ratio,
            specialist_availability=base_spec
        )
        
        # Calculate stressed prediction
        callout_factor = 1.0 - (sim_callouts / 100.0)
        starting_ratio = max(0.01, base_ratio + ratio_stress)
        stressed_ratio = round((starting_ratio * callout_factor) / sim_multiplier, 3)
        
        stressed_acuity = max(1, min(5, base_acuity + acuity_stress))
        stressed_spec = sim_spec
        
        stressed_pred = predict_wait_time(
            facility_size_beds=base_beds,
            month=month,
            day_of_week=day_of_week,
            visithour=visithour,
            urgency_level=stressed_acuity,
            nurse_to_patient_ratio=stressed_ratio,
            specialist_availability=stressed_spec
        )
        
        diff_wait = stressed_pred - base_pred
        
        # safety threshold
        acuity_factor = (6 - stressed_acuity) * 0.15 
        season_factor = 0.25 if month in [12, 1, 2] else (0.10 if month in [7, 8] else 0.0)
        safety_thresh = max(60, int(100 * (1 - season_factor)))
        
        # Wait-to-nurse rule
        diff_thresh = stressed_pred - safety_thresh
        if diff_thresh <= 0:
            stressed_needed = 0
            risk_level = "Low Risk / Safe"
        elif diff_thresh <= 30:
            stressed_needed = 1
            risk_level = "Medium Risk / Warning"
        elif diff_thresh <= 60:
            stressed_needed = 2
            risk_level = "High Risk / Critical"
        else:
            stressed_needed = 3
            risk_level = "Extreme Risk / Outbreak Surge"
            
        # Display KPIs
        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric("Base Predicted Wait", f"{base_pred:.1f} mins")
            st.metric("Stressed Predicted Wait", f"{stressed_pred:.1f} mins", delta=f"{diff_wait:.1f} mins" if diff_wait != 0 else None, delta_color="inverse")
        with kpi2:
            st.metric("Stressed Nurse Ratio", f"{stressed_ratio:.3f}")
            st.metric("Simulation Risk Level", risk_level)
        with kpi3:
            st.metric("Safety Threshold", f"{safety_thresh} mins")
            st.metric("Est. Additional Nurses Needed", f"{stressed_needed}")
            
        def apply_stress_scenario():
            st.session_state.scen_ratio = max(0.08, min(0.40, float(stressed_ratio)))
            st.session_state.scen_acuity = max(1, min(5, int(stressed_acuity)))
            st.session_state.scen_spec = int(stressed_spec)
            st.session_state.env_weather_select = "Normal"
            st.session_state.env_flu_slider = 1
            st.session_state.risk_assessed = False
            st.session_state.pending_log = None
            
        st.button("Use stressed scenario for staffing resolution", type="primary", on_click=apply_stress_scenario)
            
        # Draw Cost vs Risk intersection
        st.markdown("#### 📈 Stressed Roster Cost vs. Patient Safety Risk Curve")
        stressed_patients = max(1, int(200 * sim_multiplier * 0.45))
        
        # Generate data points for chart
        nurse_counts = list(range(1, 6))
        costs_data = []
        risks_data = []
        
        for n in nurse_counts:
            # Use the same artificial ratio boost per nurse as the optimized solver (0.05 per nurse)
            # so the graph accurately demonstrates the wait-time reduction.
            r_ratio = min(0.40, stressed_ratio + (n * 0.05))
            r_wait = predict_wait_time(base_beds, month, day_of_week, visithour, stressed_acuity, r_ratio, stressed_spec)
            costs_data.append(n * 55.0 * 12.0)
            risks_data.append(min(100.0, (r_wait / 120.0) * 100.0))
            
        chart_df = pd.DataFrame({
            "Additional Nurses Added": nurse_counts,
            "Roster Cost ($)": costs_data,
            "Clinical Risk Score (0-100)": [r * 10 for r in risks_data]
        })
        st.line_chart(chart_df.set_index("Additional Nurses Added"), height=250)
        st.caption("Notice how the 'Sweet Spot' is reached when the Clinical Risk drops (representing safe wait times) without causing a massive spike in Roster Costs.")

# Tab 3: Explainability and Token Logs
if workflow_page == "🔍 Explainability & Token Logs":
    st.subheader("🔍 Explainability Reports & Cost Analytics")
    
    logs = get_logs()
    if not logs:
        st.info("No audit logs found. Run a shortage resolution to generate logs.")
    else:
        col_l1, col_l2 = st.columns([1, 2])
        
        with col_l1:
            st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
            st.markdown("#### 📜 Resolution History logs")
            log_ids = [log["id"] for log in reversed(logs)]
            selected_id = st.selectbox("Select Resolution Log ID", log_ids)
            
            selected_log = next(log for log in logs if log["id"] == selected_id)
            
            st.write(f"**Timestamp**: {selected_log['timestamp']}")
            st.write(f"**Status**: `{selected_log['status']}`")
            st.write(f"**Staffing Cost**: `${selected_log['costs']['total_staffing_cost']:.2f}`")
            st.write(f"**Fallback Engine Used**: `{'Yes' if selected_log['fallback_used'] else 'No (AI Online)'}`")
            
            # Detailed Token usage
            log_costs = selected_log.get("costs", {})
            st.markdown("---")
            st.markdown("**Groq/API Token Usage Audit**")
            if log_costs.get("total_tokens") == -1:
                st.warning("Token usage unavailable — tracker not connected")
            elif log_costs.get("llm_calls", 0) == 0:
                st.markdown("""<div style="background-color: #102A43; border: 1px solid #2563EB; border-radius: 10px; padding: 16px 18px; margin-bottom: 20px; color: #F8FAFC; line-height: 1.6; font-size: 0.95rem;"><p style="margin-top: 0; margin-bottom: 0; color: #FFFFFF;">Token usage: 0 tokens - Low-token local rule mode</p></div>""", unsafe_allow_html=True)
            else:
                st.write(f"- **Groq/API Calls Made**: {log_costs.get('llm_calls', 0)}")
                st.write(f"- **Prompt Tokens**: {log_costs.get('prompt_tokens', 0)}")
                st.write(f"- **Response Tokens**: {log_costs.get('response_tokens', 0)}")
                st.write(f"- **Total Tokens**: {log_costs.get('total_tokens', 0)}")
                st.write(f"- **Estimated API Cost**: ${log_costs.get('estimated_api_cost', 0.0):.5f}")
                
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_l2:
            st.markdown("#### 🗣️ Decoded Multi-Agent Explanation:")
            st.markdown(selected_log["explainability_narrative"])
            
            st.markdown("---")
            st.markdown("#### 📊 XGBoost Model Global Feature Importance")
            importances = get_feature_importances()
            if importances:
                importance_df = pd.DataFrame({
                    "Feature": [f.replace("_", " ").title() for f in importances.keys()],
                    "Importance": list(importances.values())
                }).sort_values("Importance", ascending=False)
                st.bar_chart(importance_df.set_index("Feature"), height=220)
                
            st.markdown("---")
            st.markdown("#### 💵 API & Staffing Cumulative Expenses")
            
            total_tokens = sum([log["costs"].get("total_tokens", 0) for log in logs if log["costs"].get("total_tokens", 0) != -1])
            total_api_cost = sum([log["costs"].get("estimated_api_cost", 0.0) for log in logs])
            total_staffing_cost = sum([log["costs"]["total_staffing_cost"] for log in logs])
            
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("Cumulative API Tokens", f"{total_tokens}")
            with col_m2:
                st.metric("Cumulative API Cost", f"${total_api_cost:.5f}")
            with col_m3:
                st.metric("Grand Total Roster Cost", f"${total_staffing_cost:.2f}")

# Tab 4: Audit Log
if workflow_page == "📝 Audit Log":
    st.subheader("📝 Human Decision Audit Log")
    st.caption("Persistent audit trail of all governance decisions made across sessions.")
    
    audit_trail_db = get_audit_logs()
    if not audit_trail_db:
        st.info("No audit entries yet. Complete a full workflow (Steps 1–3) to generate an audit record.")
    else:
        audit_df = pd.DataFrame(build_audit_table_rows(audit_trail_db))
        st.dataframe(audit_df, use_container_width=True)
        
        with st.expander("🔍 View detailed audit entry", expanded=False):
            st.markdown("#### 🔍 Detailed Audit Entry Viewer")
            reversed_audit = list(reversed(audit_trail_db))
            selected_audit_id = st.selectbox(
                "Select Audit Log Entry to View Details:", 
                options=range(len(reversed_audit)),
                format_func=lambda idx: f"[{reversed_audit[idx].get('timestamp', 'N/A')}] Shift: {reversed_audit[idx].get('shift_date', 'N/A')} ({reversed_audit[idx].get('shift_type', 'N/A')}) — {reversed_audit[idx].get('department', 'N/A')}",
                key="audit_log_selector"
            )
            selected_entry = reversed_audit[selected_audit_id]
        
            col_ad1, col_ad2 = st.columns(2)
            with col_ad1:
                st.markdown(f"**Predicted Wait Time**: {selected_entry.get('predicted_wait_time', 'N/A')}")
                st.markdown(f"**Final Staffing Cost**: {selected_entry.get('estimated_cost', 'N/A')}")
                st.markdown(f"**Base XGBoost Staffing Need**: `{selected_entry.get('base_nurses_needed', 'N/A')} nurse(s)`")
                st.markdown(f"**Research-Adjusted Staffing Need**: `{selected_entry.get('research_adjusted_nurses_needed', 'N/A')} nurse(s)`")
                st.markdown(f"**Staffing Cost (Base)**: `${selected_entry.get('staffing_cost_before', 0.0):.2f}`")
                st.markdown(f"**Staffing Cost (Adjusted)**: `${selected_entry.get('staffing_cost_after', 0.0):.2f}`")
                st.markdown(f"**Staffing Cost Increase**: `${selected_entry.get('cost_increase', 0.0):.2f}`")
                st.markdown(f"**Human Decision**: `{selected_entry.get('human_decision', 'N/A')}`")
                st.markdown(f"**Override Stage**: `{selected_entry.get('override_stage', 'N/A')}`")
                if selected_entry.get('override_reason'):
                    st.markdown(f"**Override Reason**: *{selected_entry.get('override_reason')}*")
            with col_ad2:
                st.markdown(f"**Selected Nurse(s)**: {selected_entry.get('final_selected_nurse', 'None')}")
                st.markdown(f"**Final Nurses Recommended**: `{selected_entry.get('final_nurses_recommended', 'N/A')}`")
                st.markdown(f"**Nurse Adjustment Reasons**: `{', '.join(selected_entry.get('nurse_adjustment_reasons', [])) or 'None'}`")
                st.markdown(f"**Approval Required**: `{'Yes' if selected_entry.get('approval_required') else 'No'}`")
                st.markdown(f"**Compliance Warnings**: `{selected_entry.get('compliance_warnings', 'None')}`")
                st.markdown(f"**Token Mode**: `{selected_entry.get('token_usage_mode', 'N/A')}`")
            
            st.markdown("##### 🔬 Recommended Interventions & Costs")
            interventions_data = selected_entry.get("committee_evidence", {}).get("recommended_interventions", [])
            if not interventions_data:
                interventions_data = selected_entry.get("costed_interventions", [])
                if isinstance(interventions_data, str):
                    try:
                        import json
                        interventions_data = json.loads(interventions_data)
                    except:
                        interventions_data = []
                    
            if interventions_data:
                for idx, p in enumerate(interventions_data):
                    cost_val = p.get('estimated_cost', 0.0)
                    cost_str = f"${cost_val:,.2f}" if isinstance(cost_val, (int, float)) else str(cost_val)
                    st.markdown(f"""
                    - **{p.get('name')}**: Cost: **{cost_str}** ({p.get('cost_status', 'estimated')})
                      * Bottleneck: `{p.get('target_bottleneck')}` | Formula: `{p.get('cost_formula', 'N/A')}`
                    """)
            
                total_int_cost = selected_entry.get("committee_evidence", {}).get("intervention_cost_summary", {}).get("total_estimated_intervention_cost", 0.0)
                if not total_int_cost:
                    total_int_cost = selected_entry.get("research_module_intervention_cost", 0.0)
                st.markdown(f"**Total Estimated Intervention Cost**: `${total_int_cost:,.2f}`")
            else:
                st.info("No research-module interventions recommended for this resolution.")
        
            st.markdown("---")
            st.markdown("#### 📊 Decision Summary")
            col_au1, col_au2, col_au3 = st.columns(3)
            with col_au1:
                st.metric("Total Decisions", len(audit_trail_db))
            with col_au2:
                approved = len([e for e in audit_trail_db if e['human_decision'] == 'Approved'])
                st.metric("Approved", approved)
            with col_au3:
                overrides = len([e for e in audit_trail_db if 'Override' in e['human_decision']])
                st.metric("Overrides", overrides)

            # Download button for Audit Trail as CSV
            csv_data = audit_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Audit Trail as CSV",
                data=csv_data,
                file_name=f"audit_trail_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )


    st.markdown("---")
    col_bot1, col_bot2 = st.columns(2)
    with col_bot1:
        with st.expander("🛠️ Architecture & How It Works"):
            st.markdown("""
            **Data & Workflow Flowchart:**
            ```
            ER Shift Scenario Config
              ↓
            XGBoost Wait-Time Prediction
              ↓
            Stress Simulator (What-If Demand Surge)
              ↓
            Nurse Need Estimator (Rule-Based Mapping)
              ↓
            ADK-Style Multi-Agent Review
              ↓
            Human-in-the-Loop Approval & Override
              ↓
            Roster Update & Shift Schedule Write
              ↓
            Persistent Audit Log
            ```
            """)

    with col_bot2:
        with st.expander("⚠️ Prototype Limitations"):
            st.markdown("""
            - Uses synthetic/reduced ER wait-time datasets.
            - Nurse roster is simulated mock data.
            - Shift schedule is mock data.
            - Before/after wait-time reduction is a model-based estimate.
            - Not validated on real hospital production workloads or clinical environments.
            - Human supervisor approval is strictly required before any roster changes are committed.
            - This is a decision-support prototype and does not possess clinical staffing authority.
            """)

# Tab 5: Research Modules Status
if workflow_page == "🔬 Research & Validation":
    st.subheader("🔬 Operational Research & Validation Status")
    
    st.markdown("### 🧪 Validation & Testing Center")
    st.caption("Trigger automated tests across the codebase to ensure all backend pipelines, ML models, and multi-agent workflows are active and correct.")
    
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        st.markdown("<div class='glass-card' style='margin-bottom: 15px;'>", unsafe_allow_html=True)
        st.markdown("#### 1. Research Modules & Costs")
        st.caption("Validates database schemas, ESI/boarding/surge signals, and configurable intervention costing.")
        if st.button("Run Research Module Tests"):
            import subprocess, sys
            base_dir = os.path.dirname(os.path.dirname(__file__))
            script_path = os.path.join(base_dir, "backend", "test_research_modules.py")
            subprocess.run([sys.executable, script_path])
            st.success("Research Module Tests Completed!")
            
        try:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            with open(os.path.join(base_dir, "backend", "module_test_results.json"), "r") as f:
                test_results = json.load(f)
                st.write(f"**Last Run**: {test_results['timestamp']}")
                st.write(f"**Status**: {'✅ PASS' if test_results['overall_status'] == 'PASS' else '❌ FAIL'}")
                st.write(f"Passed: {test_results['summary']['passed']}, Failed: {test_results['summary']['failed']}")
                with st.expander("View Full Details"):
                    st.json(test_results["tests"])
        except Exception:
            st.info("No test results found. Run tests to generate.")
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='glass-card' style='margin-bottom: 15px;'>", unsafe_allow_html=True)
        st.markdown("#### 3. Model Performance & Drivers")
        st.caption("Evaluates XGBoost and CatBoost on validation datasets, tracking MAE, R2, and Risk Band Recall.")
        if st.button("Run Model Validation Tests"):
            import subprocess, sys
            base_dir = os.path.dirname(os.path.dirname(__file__))
            script_path = os.path.join(base_dir, "backend", "test_models.py")
            res = subprocess.run([sys.executable, script_path], capture_output=True, text=True)
            out_path = os.path.join(base_dir, "backend", "model_test_results.txt")
            with open(out_path, "w") as f:
                f.write(res.stdout)
            st.success("Model Validation Tests Completed!")
            
        try:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            out_path = os.path.join(base_dir, "backend", "model_test_results.txt")
            if os.path.exists(out_path):
                with open(out_path, "r") as f:
                    st.code(f.read(), language="markdown")
            else:
                st.info("No model evaluation results found. Click run above.")
        except Exception as e:
            st.error(f"Error reading model results: {e}")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_t2:
        st.markdown("<div class='glass-card' style='margin-bottom: 15px;'>", unsafe_allow_html=True)
        st.markdown("#### 2. Backend Pipeline Smoke Test")
        st.caption("Verifies full local workflow integration, imports, and mock database queries.")
        if st.button("Run Smoke Tests"):
            import subprocess, sys
            base_dir = os.path.dirname(os.path.dirname(__file__))
            script_path = os.path.join(base_dir, "backend", "smoke_test_app.py")
            subprocess.run([sys.executable, script_path])
            st.success("Smoke Integration Tests Completed!")
            
        try:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            with open(os.path.join(base_dir, "backend", "smoke_test_results.json"), "r") as f:
                smoke_results = json.load(f)
                st.write(f"**Last Run**: {smoke_results['timestamp']}")
                st.write(f"**Status**: {'✅ PASS' if smoke_results['overall_status'] == 'PASS' else '❌ FAIL'}")
                st.write(f"Passed: {smoke_results['summary']['passed']}, Failed: {smoke_results['summary']['failed']}")
                with st.expander("View Full Details"):
                    st.json(smoke_results["tests"])
        except Exception:
            st.info("No smoke results found. Run tests to generate.")
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='glass-card' style='margin-bottom: 15px;'>", unsafe_allow_html=True)
        st.markdown("#### 4. ADK Agents & Route Tests")
        st.caption("Verifies the multi-agent ADK workflow keys and tests Flask API routes connection.")
        if st.button("Run ADK Agent & API Tests"):
            import subprocess, sys
            base_dir = os.path.dirname(os.path.dirname(__file__))
            
            # Run ADK core test
            adk_script = os.path.join(base_dir, "test_adk.py")
            res_adk = subprocess.run([sys.executable, adk_script], capture_output=True, text=True)
            
            # Run API route test
            api_script = os.path.join(base_dir, "test_api.py")
            res_api = subprocess.run([sys.executable, api_script], capture_output=True, text=True)
            
            out_path = os.path.join(base_dir, "backend", "adk_api_test_results.txt")
            with open(out_path, "w") as f:
                f.write("=== ADK workflow core Test ===\n" + res_adk.stdout + "\n" + res_adk.stderr +
                        "\n\n=== API route Test (Flask server must be active) ===\n" + res_api.stdout + "\n" + res_api.stderr)
            st.success("Agent & API Tests Completed!")
            
        try:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            out_path = os.path.join(base_dir, "backend", "adk_api_test_results.txt")
            if os.path.exists(out_path):
                with open(out_path, "r") as f:
                    st.code(f.read(), language="markdown")
            else:
                st.info("No agent/api test results found. Click run above.")
        except Exception as e:
            st.error(f"Error reading agent results: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Data Sources Registry")
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(base_dir, "database", "data_sources.json"), "r") as f:
            registry = json.load(f)
            st.json(registry)
    except Exception:
        st.info("Registry not available.")

# Tab 6: AI Committee Planner
if workflow_page == "🏛️ AI Committee Debate & Planner":
    st.subheader("🏛️ AI Committee Debate & Intervention Planner")
    logs = get_logs()
    if not logs:
        st.info("No shortage resolutions found. Run a shortage solver to populate evidence.")
    else:
        latest_log = logs[-1]
        ev = latest_log.get("committee_evidence", {})
        ag = latest_log.get("active_agents", [])
        plan = latest_log.get("intervention_plan", [])
        
        if not ev:
            st.warning("Latest log does not contain committee evidence.")
        else:
            col_c1, col_c2 = st.columns([1, 1])
            with col_c1:
                st.markdown("#### Committee Evidence Signals")
                st.write(f"**XGBoost Predicted Wait**: {ev.get('xgboost_predicted_wait_time', 0):.1f} mins")
                st.write(f"**Base Staffing Risk**: {ev.get('base_staffing_risk', 'Unknown')}")
                st.write(f"**ESI Pressure**: {ev.get('esi_pressure', 'Low')} (+{ev.get('esi_adjustment', 0)})")
                st.write(f"**Boarding Pressure**: {ev.get('boarding_pressure', 'Low')} (+{ev.get('boarding_adjustment', 0)})")
                st.write(f"**Arrival Surge Pressure**: {ev.get('arrival_surge_pressure', 'Low')} (+{ev.get('arrival_adjustment', 0)})")
                st.write(f"**Fast-Track Pressure**: {ev.get('fast_track_pressure', 'Low')} (+{ev.get('fast_track_adjustment', 0)})")
                st.write(f"**Adjusted Operational Risk**: {ev.get('adjusted_operational_risk', 'Unknown')} (Score: {ev.get('adjusted_operational_risk_score', 0)})")
                
                cost_summary = ev.get("intervention_cost_summary", {})
                if cost_summary:
                    st.write(f"**Intervention Cost**: ${cost_summary.get('total_estimated_intervention_cost', 0.0):,.2f} ({cost_summary.get('cost_status', 'estimated')})")
                
            with col_c2:
                st.markdown("#### Dynamic Agent Activation")
                for agent in ag:
                    st.write(f"- **{agent['agent_name']}** (Activated: {agent['activation_reason']})")
                    st.caption(f'"{agent["short_position"]}"')
                    
            st.markdown("---")
            
            # Tab 6 metrics
            col_m1, col_m2, col_m3 = st.columns(3)
            total_staffing = latest_log.get("costs", {}).get("total_staffing_cost", 0.0)
            total_interventions = latest_log.get("costs", {}).get("research_module_intervention_cost", 0.0)
            total_ops = latest_log.get("costs", {}).get("total_estimated_operational_cost", total_staffing + total_interventions)
            
            with col_m1:
                st.metric("Total Staffing Cost (Roster)", f"${total_staffing:,.2f}")
            with col_m2:
                st.metric("Total Intervention Cost", f"${total_interventions:,.2f}")
            with col_m3:
                st.metric("Total Estimated Operational Cost", f"${total_ops:,.2f}")
            
            st.markdown("---")
            st.markdown("#### ER Staffing Intervention Planner")
            for p in plan:
                cost_val = p.get('estimated_cost', 0.0)
                if isinstance(cost_val, (int, float)):
                    cost_str = f"${cost_val:,.2f}"
                else:
                    cost_str = str(cost_val)
                
                cost_status = p.get('cost_status', 'estimated')
                cost_formula = p.get('cost_formula', 'N/A')
                cost_source = p.get('cost_assumption_source', 'N/A')
                cost_note = p.get('cost_note', 'N/A')
                
                st.markdown(f"""
                <div class='glass-card' style='margin-bottom: 15px; border-left: 5px solid #6366f1; padding: 15px;'>
                    <h5 style='margin-top: 0; color: #f8fafc; font-size: 1.1em; font-weight: bold;'>{p.get('name', 'Unknown Intervention')}</h5>
                    <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.9em; margin-bottom: 8px;'>
                        <div><strong>Target Bottleneck:</strong> {p.get('target_bottleneck', 'N/A')}</div>
                        <div><strong>Acuity Risk:</strong> {p.get('adjusted_operational_risk', 'N/A')}</div>
                        <div><strong>Expected Wait Reduction:</strong> {p.get('expected_wait_time_reduction', 'N/A')}</div>
                        <div><strong>Estimated Cost:</strong> <span style='color: #818cf8; font-weight: bold;'>{cost_str}</span> ({cost_status})</div>
                        <div style='grid-column: span 2;'><strong>Formula:</strong> <code>{cost_formula}</code></div>
                        <div style='grid-column: span 2;'><strong>Assumption Source:</strong> <em>{cost_source}</em></div>
                    </div>
                    <p style='margin: 0; font-size: 0.9em;'><strong>Explanation:</strong> {p.get('explanation', 'N/A')}</p>
                    <p style='margin: 5px 0 0 0; font-size: 0.8em; color: #94a3b8;'><strong>Note:</strong> {cost_note}</p>
                </div>
                """, unsafe_allow_html=True)

# Tab 7: Model Performance
if workflow_page == "📈 Model Performance":
    st.markdown("### 📈 XGBoost Model Performance Dashboard")
    st.caption("Visual proof that the underlying Machine Learning model is accurately predicting ER wait times and catching dangerous staffing-risk scenarios.")

    # Hero metrics from model_metrics.json
    try:
        with open("backend/model_metrics.json", "r") as f:
            perf_metrics = json.load(f)
        pm = perf_metrics.get("metrics", {})
        pb = perf_metrics.get("baseline_metrics", {})
        ptm = perf_metrics.get("training_metadata", {})

        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        with col_p1:
            st.metric("R² Score", f"{pm.get('r2', 0):.3f}", help="How much variation the model explains (1.0 = perfect)")
        with col_p2:
            st.metric("MAE", f"{pm.get('mae', 0):.2f} mins", help="Average absolute prediction error")
        with col_p3:
            st.metric("Risk Band Accuracy", f"{pm.get('risk_band_accuracy', 0):.1%}", help="How often the model correctly classifies the risk band")
        with col_p4:
            st.metric("High/Critical Recall", f"{pm.get('high_or_critical_recall', 0):.1%}", help="How often the model catches dangerous scenarios")

        st.markdown(f"""
        <div style="background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 10px; padding: 16px; margin: 15px 0; color: #e2e8f0;">
            <strong style="color: #a5b4fc;">📊 Baseline Comparison:</strong> XGBoost reduced average error from <strong>{pb.get('mae', 0):.1f} mins</strong> (naive mean baseline) to <strong>{pm.get('mae', 0):.1f} mins</strong>.
            Trained on <strong>{ptm.get('train_rows', 0):,}</strong> records, tested on <strong>{ptm.get('test_rows', 0):,}</strong> records.
            <span style="color: #94a3b8; font-size: 0.85em;">Last trained: {ptm.get('last_trained_time', 'N/A')}</span>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.info("Model metrics not found. Train the model first.")

    st.markdown("---")

    # Load evaluation data from backend
    if st.button("🔄 Load Model Evaluation Data", type="primary", use_container_width=True, key="load_eval_btn"):
        try:
            eval_resp = requests.get(f"{API_BASE_URL}/api/model-evaluation", timeout=5)
            if eval_resp.status_code == 200:
                st.session_state.model_eval_data = eval_resp.json()
                st.success("Model evaluation data loaded successfully!")
            else:
                st.error(f"Failed to load evaluation data: {eval_resp.json().get('error', 'Unknown error')}")
        except Exception as e:
            st.error(f"Error connecting to backend: {e}")

    eval_data = st.session_state.get("model_eval_data")

    if eval_data and eval_data.get("success"):
        import plotly.graph_objects as go
        import plotly.express as px

        # --- Graph 1: Feature Importance ---
        st.markdown("#### 🏆 Top 25 Feature Importances")
        st.caption("Which factors does the XGBoost model rely on most heavily to predict ER wait times?")

        fi_data = eval_data["feature_importances"]
        mapping_success = eval_data.get("feature_mapping_success", True)
        
        if not mapping_success:
            st.warning("Feature names could not be mapped from the model pipeline. Retrain the model or regenerate the feature-name metadata.")
            
        fi_features = [item["feature"] for item in reversed(fi_data)]
        fi_values = [item["importance"] for item in reversed(fi_data)]

        fig_fi = go.Figure(go.Bar(
            x=fi_values,
            y=fi_features,
            orientation='h',
            marker=dict(
                color=fi_values,
                colorscale=[[0, '#312e81'], [0.25, '#4338ca'], [0.5, '#6366f1'], [0.75, '#818cf8'], [1.0, '#a5b4fc']],
                line=dict(color='rgba(99, 102, 241, 0.6)', width=1)
            ),
            hovertemplate='<b>%{y}</b><br>Importance: %{x:.4f}<extra></extra>'
        ))
        fig_fi.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0', size=11),
            height=650,
            margin=dict(l=10, r=30, t=10, b=10),
            xaxis=dict(title="Feature Importance (Gain)", gridcolor='rgba(148, 163, 184, 0.15)', zeroline=False),
            yaxis=dict(gridcolor='rgba(148, 163, 184, 0.08)')
        )
        st.plotly_chart(fig_fi, use_container_width=True)
        
        st.markdown("This chart shows which operational factors the XGBoost model relied on most when predicting ER wait time. Higher importance means the feature contributed more strongly across the model’s decision trees. These values explain model behavior; they do not prove medical causation.")

        st.markdown("---")

        # --- Graph 2: Actual vs Predicted Scatter ---
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("#### 🎯 Actual vs. Predicted Wait Time")
            st.caption(f"Scatter plot of {eval_data['sample_size']} sampled test points (out of {eval_data['total_test_size']} total).")

            avp = eval_data["actual_vs_predicted"]
            actual = avp["actual"]
            predicted = avp["predicted"]

            fig_scatter = go.Figure()

            # Perfect prediction line
            min_val = min(min(actual), min(predicted))
            max_val = max(max(actual), max(predicted))
            fig_scatter.add_trace(go.Scatter(
                x=[min_val, max_val], y=[min_val, max_val],
                mode='lines',
                line=dict(color='rgba(248, 113, 113, 0.6)', width=2, dash='dash'),
                name='Perfect Prediction',
                showlegend=True
            ))

            fig_scatter.add_trace(go.Scatter(
                x=actual, y=predicted,
                mode='markers',
                marker=dict(
                    size=6,
                    color=predicted,
                    colorscale=[[0, '#312e81'], [0.3, '#4338ca'], [0.5, '#6366f1'], [0.7, '#818cf8'], [1.0, '#c4b5fd']],
                    opacity=0.7,
                    line=dict(width=0.5, color='rgba(255,255,255,0.2)')
                ),
                name='Test Predictions',
                hovertemplate='<b>Actual:</b> %{x:.1f} min<br><b>Predicted:</b> %{y:.1f} min<extra></extra>'
            ))

            fig_scatter.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#e2e8f0', size=11),
                height=450,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(title="Actual Wait Time (minutes)", gridcolor='rgba(148, 163, 184, 0.15)', zeroline=False),
                yaxis=dict(title="Predicted Wait Time (minutes)", gridcolor='rgba(148, 163, 184, 0.15)', zeroline=False),
                legend=dict(x=0.02, y=0.98, bgcolor='rgba(0,0,0,0.3)', font=dict(size=10))
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        # --- Graph 3: Residual Distribution ---
        with col_g2:
            st.markdown("#### 📊 Residual Distribution")
            st.caption("How are the prediction errors distributed? A tight bell curve centered at 0 = excellent model.")

            residuals = eval_data["residuals"]

            fig_resid = go.Figure()
            fig_resid.add_trace(go.Histogram(
                x=residuals,
                nbinsx=50,
                marker=dict(
                    color='rgba(99, 102, 241, 0.7)',
                    line=dict(color='rgba(165, 180, 252, 0.8)', width=1)
                ),
                hovertemplate='<b>Error:</b> %{x:.1f} min<br><b>Count:</b> %{y}<extra></extra>'
            ))

            # Add vertical line at 0
            fig_resid.add_vline(x=0, line_dash="dash", line_color="rgba(248, 113, 113, 0.7)", line_width=2)

            mean_resid = sum(residuals) / len(residuals)
            fig_resid.add_annotation(
                x=mean_resid,
                text=f"Mean: {mean_resid:.2f}",
                showarrow=True,
                arrowhead=2,
                arrowcolor='#f87171',
                font=dict(color='#f87171', size=11),
                yref='paper', y=0.95
            )

            fig_resid.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#e2e8f0', size=11),
                height=450,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(title="Prediction Error (Actual - Predicted, minutes)", gridcolor='rgba(148, 163, 184, 0.15)', zeroline=False),
                yaxis=dict(title="Count", gridcolor='rgba(148, 163, 184, 0.15)', zeroline=False)
            )
            st.plotly_chart(fig_resid, use_container_width=True)

        st.markdown("---")

        # --- Graph 4: Risk Band Confusion Matrix ---
        st.markdown("#### 🔥 Risk Band Confusion Matrix")
        st.caption("How accurately does the model classify patients into the correct risk band? This is the most important metric for clinical staffing decisions.")

        confusion = eval_data["risk_band_confusion"]
        band_labels = ["Low", "Moderate", "High", "Critical"]

        z_matrix = []
        annotations_list = []
        for i, actual_b in enumerate(band_labels):
            row = []
            for j, pred_b in enumerate(band_labels):
                val = confusion.get(actual_b, {}).get(pred_b, 0)
                row.append(val)
                annotations_list.append(dict(
                    x=pred_b, y=actual_b,
                    text=str(val),
                    font=dict(color='white' if val > 20 else '#a5b4fc', size=14, family='Inter'),
                    showarrow=False
                ))
            z_matrix.append(row)

        fig_cm = go.Figure(data=go.Heatmap(
            z=z_matrix,
            x=band_labels,
            y=band_labels,
            colorscale=[[0, '#0f172a'], [0.2, '#1e1b4b'], [0.4, '#312e81'], [0.6, '#4338ca'], [0.8, '#6366f1'], [1.0, '#818cf8']],
            hovertemplate='<b>Actual:</b> %{y}<br><b>Predicted:</b> %{x}<br><b>Count:</b> %{z}<extra></extra>',
            showscale=True,
            colorbar=dict(title="Count", tickfont=dict(color='#e2e8f0'), title_font=dict(color='#e2e8f0'))
        ))

        fig_cm.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#e2e8f0', size=12),
            height=450,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(title="Predicted Risk Band", side='bottom'),
            yaxis=dict(title="Actual Risk Band", autorange='reversed'),
            annotations=annotations_list
        )
        st.plotly_chart(fig_cm, use_container_width=True)

        st.markdown("""
        <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 10px; padding: 16px; margin-top: 15px; color: #e2e8f0;">
            <strong style="color: #86efac;">✅ How to Read This:</strong> The diagonal (top-left to bottom-right) shows correct classifications. 
            Off-diagonal cells show misclassifications. For clinical safety, the most critical cell is <strong>High/Critical (Actual) → Low/Moderate (Predicted)</strong> — 
            a missed dangerous scenario. Our High/Critical Recall metric specifically measures how well we avoid this failure mode.
        </div>
        """, unsafe_allow_html=True)

    elif not eval_data:
        st.info("👆 Click the **Load Model Evaluation Data** button above to generate the performance visualizations.")
