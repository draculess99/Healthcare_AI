import os
import pandas as pd
import functools

def _get_db_path(filename):
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", filename)

@functools.lru_cache(maxsize=1)
def _get_esi_df():
    return pd.read_csv(_get_db_path("esi_seasonal_patterns.csv"))

@functools.lru_cache(maxsize=1)
def _get_boarding_df():
    return pd.read_csv(_get_db_path("bed_boarding_pressure.csv"))

@functools.lru_cache(maxsize=1)
def _get_arrival_df():
    return pd.read_csv(_get_db_path("arrival_surge_pressure.csv"))

@functools.lru_cache(maxsize=1)
def _get_fast_track_df():
    return pd.read_csv(_get_db_path("fast_track_flow.csv"))

def get_seasonal_esi_pressure(month, preset_data=None):
    source_type = "CSV lookup"
    timeline_match_level = "Month Match"
    try:
        df = _get_esi_df()
        row = df[df["month"] == month].iloc[0]
        pressure = row["seasonal_acuity_pressure"]
        note = row["data_source_note"]
    except Exception:
        pressure = "Low"
        note = "Fallback due to missing file"
        
    if preset_data and "patient_acuity_proxy" in preset_data:
        source_type = "Demo preset override"
        timeline_match_level = "Preset Exact Match"
        acuity = preset_data["patient_acuity_proxy"]
        if acuity == 1:
            pressure = "Critical"
        elif acuity == 2:
            pressure = "High"
        elif acuity == 3:
            pressure = "Moderate"
        else:
            pressure = "Low"
        note = f"Overridden by demo preset values (acuity proxy = {acuity})"
        
    pts = 0
    if pressure == "Moderate": pts = 5
    elif pressure == "High": pts = 10
    elif pressure == "Critical": pts = 15
        
    return {
        "pressure_level": pressure,
        "risk_adjustment_points": pts,
        "explanation": f"Seasonal ESI acuity pressure is {pressure}.",
        "source_file": "database/esi_seasonal_patterns.csv",
        "data_source_note": note,
        "timeline_match_level": timeline_match_level,
        "source_type": source_type
    }

def get_bed_boarding_pressure(month, day_of_week, hour, preset_data=None):
    source_type = "CSV lookup"
    timeline_match_level = "Hour Match"
    try:
        df = _get_boarding_df()
        subset = df[(df["hour"] == hour)]
        if subset.empty:
            row = df.iloc[0]
        else:
            row = subset.iloc[0]
        pressure = row["bed_pressure_level"]
        note = row["data_source_note"]
    except Exception:
        pressure = "Low"
        note = "Fallback due to missing file"
        
    if preset_data and "ed_occupancy_percent" in preset_data and "boarding_count" in preset_data:
        source_type = "Demo preset override"
        timeline_match_level = "Preset Exact Match"
        ed_occ = preset_data["ed_occupancy_percent"]
        board_cnt = preset_data["boarding_count"]
        inpatient_occ = preset_data.get("inpatient_bed_occupancy_percent", 0)
        if ed_occ >= 95 or board_cnt >= 20 or inpatient_occ >= 95:
            pressure = "Critical"
        elif ed_occ >= 85 or board_cnt >= 10 or inpatient_occ >= 85:
            pressure = "High"
        elif ed_occ >= 75 or board_cnt >= 5 or inpatient_occ >= 75:
            pressure = "Moderate"
        else:
            pressure = "Low"
        note = f"Overridden by demo preset values (ED Occupancy = {ed_occ}%, Boarding = {board_cnt})"
        
    pts = 0
    if pressure == "Moderate": pts = 5
    elif pressure == "High": pts = 10
    elif pressure == "Critical": pts = 15
        
    return {
        "pressure_level": pressure,
        "risk_adjustment_points": pts,
        "explanation": f"ED Boarding / Bed capacity pressure is {pressure}.",
        "source_file": "database/bed_boarding_pressure.csv",
        "data_source_note": note,
        "timeline_match_level": timeline_match_level,
        "source_type": source_type
    }

def get_arrival_surge_pressure(month, day_of_week, hour, preset_data=None):
    source_type = "CSV lookup"
    timeline_match_level = "Hour Match"
    try:
        df = _get_arrival_df()
        subset = df[(df["hour"] == hour)]
        row = subset.iloc[0] if not subset.empty else df.iloc[0]
        pressure = row["waiting_room_pressure_level"]
        note = row["data_source_note"]
    except Exception:
        pressure = "Low"
        note = "Fallback due to missing file"
        
    if preset_data and "waiting_room_count" in preset_data and "arrival_surge_multiplier" in preset_data:
        source_type = "Demo preset override"
        timeline_match_level = "Preset Exact Match"
        wr_cnt = preset_data["waiting_room_count"]
        asm = preset_data["arrival_surge_multiplier"]
        if wr_cnt >= 50 or asm >= 1.8:
            pressure = "Critical"
        elif wr_cnt >= 35 or asm >= 1.4:
            pressure = "High"
        elif wr_cnt >= 20 or asm >= 1.2:
            pressure = "Moderate"
        else:
            pressure = "Low"
        note = f"Overridden by demo preset values (Waiting Room = {wr_cnt}, Surge Mult = {asm}x)"
        
    pts = 0
    if pressure == "Moderate": pts = 5
    elif pressure == "High": pts = 10
    elif pressure == "Critical": pts = 15
        
    return {
        "pressure_level": pressure,
        "risk_adjustment_points": pts,
        "explanation": f"Waiting room arrival surge pressure is {pressure}.",
        "source_file": "database/arrival_surge_pressure.csv",
        "data_source_note": note,
        "timeline_match_level": timeline_match_level,
        "source_type": source_type
    }

def get_fast_track_flow_pressure(month, day_of_week, hour, preset_data=None):
    source_type = "CSV lookup"
    timeline_match_level = "Hour Match"
    try:
        df = _get_fast_track_df()
        subset = df[(df["hour"] == hour)]
        row = subset.iloc[0] if not subset.empty else df.iloc[0]
        pressure = row["low_acuity_bottleneck_level"]
        note = row["data_source_note"]
    except Exception:
        pressure = "Low"
        note = "Fallback due to missing file"
        
    if preset_data and "fast_track_open" in preset_data and "fast_track_queue" in preset_data:
        source_type = "Demo preset override"
        timeline_match_level = "Preset Exact Match"
        ft_open = preset_data["fast_track_open"]
        ft_q = preset_data["fast_track_queue"]
        if not ft_open and ft_q >= 20:
            pressure = "Critical"
        elif not ft_open and ft_q >= 10:
            pressure = "High"
        elif ft_q >= 8:
            pressure = "Moderate"
        else:
            pressure = "Low"
        note = f"Overridden by demo preset values (Fast-track Open = {ft_open}, Queue = {ft_q})"
        
    pts = 0
    if pressure == "Moderate": pts = 3
    elif pressure == "High": pts = 7
    elif pressure == "Critical": pts = 10
        
    return {
        "pressure_level": pressure,
        "risk_adjustment_points": pts,
        "explanation": f"Fast-track / Low-acuity flow bottleneck is {pressure}.",
        "source_file": "database/fast_track_flow.csv",
        "data_source_note": note,
        "timeline_match_level": timeline_match_level,
        "source_type": source_type
    }

def calculate_adjusted_operational_risk(base_wait_time, base_staffing_risk, esi_pressure, boarding_pressure, arrival_surge_pressure, fast_track_pressure):
    # Base risk score from wait time
    if base_wait_time < 45:
        base_score = 20
    elif base_wait_time <= 89:
        base_score = 45
    elif base_wait_time <= 149:
        base_score = 70
    else:
        base_score = 90
        
    adjustments = [
        esi_pressure.get("risk_adjustment_points", 0),
        boarding_pressure.get("risk_adjustment_points", 0),
        arrival_surge_pressure.get("risk_adjustment_points", 0),
        fast_track_pressure.get("risk_adjustment_points", 0)
    ]
    
    total_adj = sum(adjustments)
    final_score = min(100, base_score + total_adj)
    
    if final_score <= 39:
        band = "Low"
    elif final_score <= 59:
        band = "Moderate"
    elif final_score <= 79:
        band = "High"
    else:
        band = "Critical"
        
    return {
        "base_risk_score": base_score,
        "module_adjustments": total_adj,
        "final_operational_risk_score": final_score,
        "adjusted_operational_risk": band,
        "explanation": f"Base wait-time risk ({base_score}) + Modules ({total_adj}) = {final_score} ({band})"
    }

def calculate_final_nurses_needed(
    predicted_wait_time,
    safety_threshold,
    adjusted_operational_risk,
    esi_pressure,
    boarding_pressure,
    arrival_surge_pressure,
    fast_track_pressure,
    nurse_fatigue_pressure,
    nurse_callout_rate=0,
    base_nurses_needed=None
):
    # 1. Base nurses from XGBoost wait-time gap:
    if (predicted_wait_time == 0 or predicted_wait_time == 0.0) and base_nurses_needed is not None:
        base_nurses = base_nurses_needed
    else:
        diff = predicted_wait_time - safety_threshold
        if diff <= 0:
            base_nurses = 0
        elif diff <= 30:
            base_nurses = 1
        elif diff <= 60:
            base_nurses = 2
        else:
            base_nurses = 3

    # 2. Operational pressure increments:
    operational_increments = 0
    nurse_increment_reasons = []

    if adjusted_operational_risk == "Critical":
        operational_increments += 1
        nurse_increment_reasons.append("Adjusted operational risk is Critical: +1 nurse")

    if arrival_surge_pressure == "Critical":
        operational_increments += 1
        nurse_increment_reasons.append("Arrival surge pressure is Critical: +1 nurse")

    if fast_track_pressure in ["High", "Critical"]:
        operational_increments += 1
        nurse_increment_reasons.append("Fast-track / low-acuity bottleneck requires triage or fast-track nurse support")

    if nurse_fatigue_pressure in ["High", "Critical"]:
        operational_increments += 1
        nurse_increment_reasons.append("Fatigue pressure requires relief or replacement nurse coverage")

    if nurse_callout_rate >= 20:
        operational_increments += 1
        nurse_increment_reasons.append("Nurse call-out rate is above 20%")

    if boarding_pressure == "Critical":
        operational_increments += 1
        nurse_increment_reasons.append("Boarding pressure is Critical; additional safety coverage is needed, but bed-flow escalation is also required")

    # 3. Cap final nurses:
    final_additional_nurses_needed = min(4, base_nurses + operational_increments)

    # 4. Return:
    return {
        "base_nurses_from_wait_time": base_nurses,
        "operational_pressure_nurse_increments": operational_increments,
        "final_additional_nurses_needed": final_additional_nurses_needed,
        "nurse_increment_reasons": nurse_increment_reasons
    }

def calculate_research_adjusted_nurse_need(base_nurses_needed, committee_evidence, max_nurses=4):
    # Backward compatibility wrapper
    pred = committee_evidence.get("xgboost_predicted_wait_time", 0.0)
    month = committee_evidence.get("scenario_month", 6)
    season_factor = 0.25 if month in [12, 1, 2] else (0.10 if month in [7, 8] else 0.0)
    safety_threshold = max(60, int(100 * (1 - season_factor)))
    
    final_calc = calculate_final_nurses_needed(
        predicted_wait_time=pred,
        safety_threshold=safety_threshold,
        adjusted_operational_risk=committee_evidence.get("adjusted_operational_risk", "Low"),
        esi_pressure=committee_evidence.get("esi_pressure", "Low"),
        boarding_pressure=committee_evidence.get("boarding_pressure", "Low"),
        arrival_surge_pressure=committee_evidence.get("arrival_surge_pressure", "Low"),
        fast_track_pressure=committee_evidence.get("fast_track_pressure", "Low"),
        nurse_fatigue_pressure=committee_evidence.get("nurse_fatigue_pressure", "Low"),
        nurse_callout_rate=committee_evidence.get("nurse_callout_rate", 0),
        base_nurses_needed=base_nurses_needed
    )
    
    return {
        "base_nurses_needed": final_calc["base_nurses_from_wait_time"],
        "research_adjusted_nurses_needed": final_calc["final_additional_nurses_needed"],
        "nurse_adjustment_reasons": final_calc["nurse_increment_reasons"],
        "nurse_adjustment_note": "Research-module pressure adjusted staffing recommendation."
    }

def create_committee_evidence(xgboost_predicted_wait_time, base_staffing_risk, esi_module, boarding_module, arrival_module, fast_track_module, nurse_fatigue_pressure="Low", nurse_compliance_status="Valid", cost_pressure="Low", base_nurses_needed=1, preset_data=None):
    risk_info = calculate_adjusted_operational_risk(
        xgboost_predicted_wait_time, 
        base_staffing_risk, 
        esi_module, 
        boarding_module, 
        arrival_module, 
        fast_track_module
    )
    
    month = 6
    if preset_data:
        month = preset_data.get("month", 6)
    season_factor = 0.25 if month in [12, 1, 2] else (0.10 if month in [7, 8] else 0.0)
    safety_threshold = max(60, int(100 * (1 - season_factor)))
    
    nurse_callout_rate = 0
    if preset_data:
        nurse_callout_rate = preset_data.get("nurse_callout_rate", 0)
        
    if preset_data and "nurse_fatigue_pressure_override" in preset_data:
        nurse_fatigue_pressure = preset_data["nurse_fatigue_pressure_override"]
    elif preset_data and "nurse_callout_rate" in preset_data:
        if preset_data["nurse_callout_rate"] >= 20:
            nurse_fatigue_pressure = "High"

    final_calc = calculate_final_nurses_needed(
        predicted_wait_time=xgboost_predicted_wait_time,
        safety_threshold=safety_threshold,
        adjusted_operational_risk=risk_info["adjusted_operational_risk"],
        esi_pressure=esi_module["pressure_level"],
        boarding_pressure=boarding_module["pressure_level"],
        arrival_surge_pressure=arrival_module["pressure_level"],
        fast_track_pressure=fast_track_module["pressure_level"],
        nurse_fatigue_pressure=nurse_fatigue_pressure,
        nurse_callout_rate=nurse_callout_rate
    )
    
    evidence = {
        "xgboost_predicted_wait_time": xgboost_predicted_wait_time,
        "base_staffing_risk": base_staffing_risk,
        "esi_pressure": esi_module["pressure_level"],
        "esi_adjustment": esi_module["risk_adjustment_points"],
        "esi_explanation": esi_module["explanation"],
        "boarding_pressure": boarding_module["pressure_level"],
        "boarding_adjustment": boarding_module["risk_adjustment_points"],
        "boarding_explanation": boarding_module["explanation"],
        "arrival_surge_pressure": arrival_module["pressure_level"],
        "arrival_adjustment": arrival_module["risk_adjustment_points"],
        "arrival_explanation": arrival_module["explanation"],
        "fast_track_pressure": fast_track_module["pressure_level"],
        "fast_track_adjustment": fast_track_module["risk_adjustment_points"],
        "fast_track_explanation": fast_track_module["explanation"],
        "nurse_fatigue_pressure": nurse_fatigue_pressure,
        "nurse_compliance_status": nurse_compliance_status,
        "cost_pressure": cost_pressure,
        "adjusted_operational_risk_score": risk_info["final_operational_risk_score"],
        "adjusted_operational_risk": risk_info["adjusted_operational_risk"],
        "recommended_interventions": [],
        "data_sources": {
            "esi": esi_module["source_file"],
            "boarding": boarding_module["source_file"],
            "arrival": arrival_module["source_file"],
            "fast_track": fast_track_module["source_file"]
        },
        "esi_timeline_match_level": esi_module.get("timeline_match_level", "Month Match"),
        "esi_source_type": esi_module.get("source_type", "CSV lookup"),
        "boarding_timeline_match_level": boarding_module.get("timeline_match_level", "Hour Match"),
        "boarding_source_type": boarding_module.get("source_type", "CSV lookup"),
        "arrival_timeline_match_level": arrival_module.get("timeline_match_level", "Hour Match"),
        "arrival_source_type": arrival_module.get("source_type", "CSV lookup"),
        "fast_track_timeline_match_level": fast_track_module.get("timeline_match_level", "Hour Match"),
        "fast_track_source_type": fast_track_module.get("source_type", "CSV lookup"),
    }
    
    if preset_data:
        evidence["selected_demo_preset"] = preset_data.get("selected_demo_preset", "Custom")
        evidence["scenario_month"] = preset_data.get("month")
        evidence["scenario_day_of_week"] = preset_data.get("day_of_week")
        evidence["scenario_hour"] = preset_data.get("hour")
        evidence["patient_inflow_multiplier"] = preset_data.get("patient_inflow_multiplier")
        evidence["nurse_callout_rate"] = preset_data.get("nurse_callout_rate")
        evidence["waiting_room_count"] = preset_data.get("waiting_room_count")
        evidence["arrival_surge_multiplier"] = preset_data.get("arrival_surge_multiplier")
        evidence["ed_occupancy_percent"] = preset_data.get("ed_occupancy_percent")
        evidence["boarding_count"] = preset_data.get("boarding_count")
        evidence["boarding_hours_avg"] = preset_data.get("boarding_hours_avg")
        evidence["low_acuity_percent"] = preset_data.get("low_acuity_percent")
        evidence["fast_track_open"] = preset_data.get("fast_track_open")
        evidence["fast_track_queue"] = preset_data.get("fast_track_queue")
    else:
        evidence["selected_demo_preset"] = "Custom"
        evidence["scenario_month"] = month
        evidence["scenario_day_of_week"] = None
        evidence["scenario_hour"] = None
        evidence["patient_inflow_multiplier"] = 1.0
        evidence["nurse_callout_rate"] = 0
        evidence["waiting_room_count"] = 0
        evidence["arrival_surge_multiplier"] = 1.0
        evidence["ed_occupancy_percent"] = 0
        evidence["boarding_count"] = 0
        evidence["boarding_hours_avg"] = 0.0
        evidence["low_acuity_percent"] = 0
        evidence["fast_track_open"] = True
        evidence["fast_track_queue"] = 0

    evidence["base_nurses_from_wait_time"] = final_calc["base_nurses_from_wait_time"]
    evidence["operational_pressure_nurse_increments"] = final_calc["operational_pressure_nurse_increments"]
    evidence["final_additional_nurses_needed"] = final_calc["final_additional_nurses_needed"]
    evidence["nurse_increment_reasons"] = final_calc["nurse_increment_reasons"]
    
    # Backwards compatibility keys
    evidence["base_nurses_needed"] = base_nurses_needed
    evidence["research_adjusted_nurses_needed"] = final_calc["final_additional_nurses_needed"]
    evidence["nurse_adjustment_reasons"] = final_calc["nurse_increment_reasons"]
    evidence["nurse_adjustment_note"] = "Research-module pressure adjusted staffing recommendation."

    return evidence


def activate_committee_agents(committee_evidence):
    agents = []
    
    # Always include these
    agents.append({
        "agent_name": "Wait-Time Forecast Agent",
        "activated": True,
        "activation_reason": "Primary prediction core",
        "signal_used": "xgboost_predicted_wait_time",
        "short_position": f"Wait-time is forecast at {committee_evidence['xgboost_predicted_wait_time']:.1f} mins. Immediate triage required."
    })
    agents.append({
        "agent_name": "Staffing Planner Agent",
        "activated": True,
        "activation_reason": "Baseline operational requirement",
        "signal_used": "base_staffing_risk",
        "short_position": f"Base staffing risk is {committee_evidence['base_staffing_risk']}. Must assign standard coverage."
    })
    agents.append({
        "agent_name": "Patient Safety Agent",
        "activated": True,
        "activation_reason": "Always active for compliance",
        "signal_used": "adjusted_operational_risk",
        "short_position": f"Operational risk is {committee_evidence['adjusted_operational_risk']}. Maintain strict ratio safety."
    })
    agents.append({
        "agent_name": "Compliance Guard",
        "activated": True,
        "activation_reason": "Always active for compliance",
        "signal_used": "nurse_compliance_status",
        "short_position": "Ensure selected nurses do not exceed maximum safe hour limits."
    })
    agents.append({
        "agent_name": "Human Supervisor Review",
        "activated": True,
        "activation_reason": "Final governance check",
        "signal_used": "all",
        "short_position": "Review AI recommendations and assert final decision."
    })
    
    # Conditionally add specialized agents
    if committee_evidence['esi_pressure'] in ['Moderate', 'High', 'Critical']:
        agents.append({
            "agent_name": "Acuity / ESI Agent",
            "activated": True,
            "activation_reason": f"ESI pressure is {committee_evidence['esi_pressure']}",
            "signal_used": "esi_pressure",
            "short_position": "High proportion of critical patients requires prioritizing ER-certified trauma nurses."
        })
        
    if committee_evidence['boarding_pressure'] in ['Moderate', 'High', 'Critical']:
        agents.append({
            "agent_name": "Bed Flow / Boarding Agent",
            "activated": True,
            "activation_reason": f"Boarding pressure is {committee_evidence['boarding_pressure']}",
            "signal_used": "boarding_pressure",
            "short_position": "Nurse staffing improves safety coverage, but wait-time reduction may be limited unless inpatient bed flow is addressed."
        })
        
    if committee_evidence['arrival_surge_pressure'] in ['Moderate', 'High', 'Critical']:
        agents.append({
            "agent_name": "Demand Surge Agent",
            "activated": True,
            "activation_reason": f"Arrival surge pressure is {committee_evidence['arrival_surge_pressure']}",
            "signal_used": "arrival_surge_pressure",
            "short_position": "Waiting room is filling rapidly. Needs dedicated triage sorting nurse to prevent unseen decompensation."
        })
        
    if committee_evidence['fast_track_pressure'] in ['Moderate', 'High', 'Critical']:
        agents.append({
            "agent_name": "Fast-Track Flow Agent",
            "activated": True,
            "activation_reason": f"Fast-track pressure is {committee_evidence['fast_track_pressure']}",
            "signal_used": "fast_track_pressure",
            "short_position": "Low-acuity patients are clogging flow. Opening fast-track lane will rapidly clear the waiting room."
        })
        
    if committee_evidence['cost_pressure'] == 'High':
        agents.append({
            "agent_name": "Financial Auditor Agent",
            "activated": True,
            "activation_reason": "Cost pressure is High",
            "signal_used": "cost_pressure",
            "short_position": "Seek regular-rate staff before using agency or overtime."
        })
        
    if committee_evidence['nurse_fatigue_pressure'] in ['Moderate', 'High', 'Critical']:
        agents.append({
            "agent_name": "Fatigue Risk Agent",
            "activated": True,
            "activation_reason": f"Nurse fatigue pressure is {committee_evidence['nurse_fatigue_pressure']}",
            "signal_used": "nurse_fatigue_pressure",
            "short_position": "High fatigue detected across roster. Avoid consecutive 12h shifts."
        })
        
    return agents

def generate_committee_debate_summary(committee_evidence, active_agents):
    highest_pressure_signal = "None"
    highest_points = -1
    for k in ["esi", "boarding", "arrival", "fast_track"]:
        pts = committee_evidence[f"{k}_adjustment"]
        if pts > highest_points:
            highest_points = pts
            pressure_key = "arrival_surge_pressure" if k == "arrival" else f"{k}_pressure"
            highest_pressure_signal = f"{k.upper()} Pressure ({committee_evidence[pressure_key]})"
            
    base_n = committee_evidence.get("base_nurses_from_wait_time", 0)
    ops_n = committee_evidence.get("operational_pressure_nurse_increments", 0)
    final_n = committee_evidence.get("final_additional_nurses_needed", 0)
    reasons = ", ".join(committee_evidence.get("nurse_increment_reasons", [])) or "None"
    
    summary = f"The XGBoost predicted wait time is {committee_evidence['xgboost_predicted_wait_time']:.1f} mins, establishing a base staffing risk of {committee_evidence['base_staffing_risk']}. "
    summary += f"After evaluating operational modules, the adjusted operational risk is {committee_evidence['adjusted_operational_risk']} (Score: {committee_evidence['adjusted_operational_risk_score']}). "
    summary += f"The highest operational pressure point is {highest_pressure_signal}. "
    
    summary += f"\n\n**Staffing Recommendation Details:**\n"
    summary += f"- **Base nurses from wait-time gap**: {base_n}\n"
    summary += f"- **Operational increments**: {ops_n}\n"
    summary += f"- **Final additional nurses needed**: {final_n}\n"
    summary += f"- **Reasons for additional nurses**: {reasons}\n"
    summary += f"- **Human supervisor approval requirement**: Required when adjusted operational risk is Critical or staffing is adjusted.\n"
    
    summary += "\n\nCommittee Positions:\n"
    for agent in active_agents:
        summary += f"- {agent['agent_name']}: {agent['short_position']}\n"
        
    summary += f"\nFinal Recommendation:\nAdjusted operational risk is {committee_evidence['adjusted_operational_risk']}. "
    summary += f"The XGBoost wait-time gap requires {base_n} additional nurse(s). Operational pressure signals add {ops_n} more nurse requirement(s) because of {reasons}. "
    summary += f"Final recommendation: add {final_n} nurse(s) and require human supervisor approval."
    
    return summary

def generate_operational_signal_impact_summary(committee_evidence):
    actions = []
    text_blocks = []
    
    text_blocks.append(f"**XGBoost Predicted Wait Time:** {committee_evidence.get('xgboost_predicted_wait_time', 0):.1f} mins")
    text_blocks.append(f"**Base Staffing Risk:** {committee_evidence.get('base_staffing_risk', 'Unknown')}")
    
    esi = committee_evidence.get('esi_pressure', 'Low')
    if esi in ['Moderate', 'High', 'Critical']:
        actions.append("deploying matched ER-certified nurse coverage")
        text_blocks.append(f"- **ESI Pressure ({esi})**: ESI pressure is {esi}, so prioritize ER-certified nurses with acuity-capable coverage.")
        
    boarding = committee_evidence.get('boarding_pressure', 'Low')
    if boarding in ['Moderate', 'High', 'Critical']:
        actions.append("adding bed-flow escalation / inpatient bed management support")
        text_blocks.append(f"- **Boarding Pressure ({boarding})**: Boarding pressure is {boarding}, so add bed-flow escalation / inpatient bed management support.")
        
    arrival = committee_evidence.get('arrival_surge_pressure', 'Low')
    if arrival in ['Moderate', 'High', 'Critical']:
        actions.append("adding triage support")
        text_blocks.append(f"- **Arrival Surge Pressure ({arrival})**: Arrival surge pressure is {arrival}, so add triage support, float-pool support, or waiting-room monitoring.")
        
    fast_track = committee_evidence.get('fast_track_pressure', 'Low')
    if fast_track in ['Moderate', 'High', 'Critical']:
        actions.append("considering fast-track activation due to low-acuity bottleneck")
        text_blocks.append(f"- **Fast-Track Pressure ({fast_track})**: Fast-track pressure is {fast_track}, so consider opening or expanding fast-track lane for lower-acuity patients.")
        
    fatigue = committee_evidence.get('nurse_fatigue_pressure', 'Low')
    if fatigue in ['Moderate', 'High', 'Critical']:
        actions.append("avoiding fatigue-risk assignments")
        text_blocks.append(f"- **Nurse Fatigue Pressure ({fatigue})**: Nurse fatigue pressure is {fatigue}, so avoid overtime-heavy or consecutive 12-hour assignments.")
        
    adj_risk = committee_evidence.get('adjusted_operational_risk', 'Unknown')
    if adj_risk == 'Critical':
        actions.append("requiring human supervisor approval because adjusted operational risk is Critical")
        text_blocks.append(f"- **Adjusted Operational Risk (Critical)**: Human supervisor approval is required before roster commitment.")
        
    if not actions:
        actions.append("deploying matched nurses based on standard safe ratios")
        
    final_rec_text = "Recommend " + ", ".join(actions[:-1]) + (", and " if len(actions) > 1 else "") + actions[-1] + "."
    
    text_blocks.append("\n**Final Recommended Action List:**")
    for act in actions:
        text_blocks.append(f"- {act}")
        
    full_text = "#### Operational Signal Impact Summary\n\n" + "\n".join(text_blocks)
    
    return {
        "summary_text": full_text,
        "triggered_actions": actions,
        "final_recommendation_text": final_rec_text
    }

def generate_intervention_plan(committee_evidence):
    try:
        from backend.intervention_costing import attach_costs_to_interventions
    except ImportError:
        from intervention_costing import attach_costs_to_interventions
    interventions = []
    
    # 1. Add 1 ER-certified nurse (always recommended)
    interventions.append({
        "action_id": "add_er_certified_nurse",
        "name": "Add 1 ER-certified nurse",
        "target_bottleneck": "Base Staffing Shortage",
        "expected_wait_time_reduction": "-15 mins",
        "adjusted_operational_risk": "Moderate" if committee_evidence.get('adjusted_operational_risk') in ["High", "Critical"] else "Low",
        "estimated_cost": 0.0,
        "explanation": "Standard staffing resolution. Provides direct bedside care."
    })
    
    # 2. Bed flow
    if committee_evidence.get('boarding_pressure') in ['High', 'Critical']:
        interventions.append({
            "action_id": "bed_flow_escalation",
            "name": "Escalate inpatient bed management",
            "target_bottleneck": "Boarding Pressure",
            "expected_wait_time_reduction": "-25 mins",
            "adjusted_operational_risk": "Moderate",
            "estimated_cost": 0.0,
            "explanation": "Addresses the root cause of ED gridlock by expediting discharges upstairs."
        })
        
    # 3. Fast track
    if committee_evidence.get('fast_track_pressure') in ['High', 'Critical']:
        interventions.append({
            "action_id": "open_fast_track_lane",
            "name": "Open fast-track lane",
            "target_bottleneck": "Low-Acuity Flow",
            "expected_wait_time_reduction": "-40 mins",
            "adjusted_operational_risk": "Low",
            "estimated_cost": 0.0,
            "explanation": "Rapidly clears the waiting room of ESI 4 and 5 patients, drastically lowering wait times."
        })
        
    # 4. Float pool
    if committee_evidence.get('base_staffing_risk') in ['High', 'Critical'] or committee_evidence.get('adjusted_operational_risk') == 'Critical':
        interventions.append({
            "action_id": "activate_float_pool",
            "name": "Activate float pool",
            "target_bottleneck": "Critical Staffing Shortage",
            "expected_wait_time_reduction": "-30 mins",
            "adjusted_operational_risk": "Moderate",
            "estimated_cost": 0.0,
            "explanation": "Pulls cross-trained nurses from other units to immediately bolster the ED."
        })

    # 5. Triage Support (Arrival Surge)
    if committee_evidence.get('arrival_surge_pressure') in ['High', 'Critical']:
        interventions.append({
            "action_id": "add_triage_support",
            "name": "Arrival surge / triage support",
            "target_bottleneck": "Waiting Room Surge",
            "expected_wait_time_reduction": "-20 mins",
            "adjusted_operational_risk": "Moderate",
            "estimated_cost": 0.0,
            "explanation": "Assigns an extra triage nurse to sort incoming patients quickly."
        })
        
    # 6. Waiting Room Monitoring
    if committee_evidence.get('arrival_surge_pressure') == 'Critical':
        interventions.append({
            "action_id": "waiting_room_monitoring",
            "name": "Waiting room monitoring",
            "target_bottleneck": "Waiting Room Overcrowding",
            "expected_wait_time_reduction": "-10 mins",
            "adjusted_operational_risk": "Low",
            "estimated_cost": 0.0,
            "explanation": "Deploys a patient advocate or nurse assistant to check on waiting patients."
        })

    # 7. Fatigue Safe Replacement
    if committee_evidence.get('nurse_fatigue_pressure') in ['High', 'Critical']:
        interventions.append({
            "action_id": "fatigue_safe_replacement",
            "name": "Fatigue-safe replacement",
            "target_bottleneck": "Nurse Burnout & Errors",
            "expected_wait_time_reduction": "0 mins (Safety)",
            "adjusted_operational_risk": "Low",
            "estimated_cost": 0.0,
            "explanation": "Brings in a rested backup nurse to replace fatigued staff."
        })
        
    return attach_costs_to_interventions(interventions)

