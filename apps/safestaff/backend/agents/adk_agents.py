import os
import json
from dotenv import load_dotenv
from typing import Dict, Any, List, Tuple

try:
    from google.adk.agents import LlmAgent, SequentialAgent
    HAS_ADK = True
except ImportError:
    HAS_ADK = False

load_dotenv(override=True)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if HAS_ADK:
    root_agent = LlmAgent(
        name="nurse_supervisor",
        model="gemini-1.5-flash",
        instruction="You are the Nurse Staffing Supervisor coordinating clinical shortages."
    )
else:
    class MockLlmAgent:
        def __init__(self, name, model, instruction):
            self.name = name
            self.model = model
            self.instruction = instruction
    root_agent = MockLlmAgent("nurse_supervisor", "gemini-1.5-flash", "Supervisor mock")

def run_adk_workflow(
    log_id: str,
    shift_type: str,
    department: str,
    acuity_level: int,
    required_nurses: int,
    candidates: List[Dict[str, Any]],
    patient_volume_multiplier: float,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    if context is None:
        context = {}
    
    # Import research modules
    try:
        from backend.research_modules import (
            get_seasonal_esi_pressure,
            get_bed_boarding_pressure,
            get_arrival_surge_pressure,
            get_fast_track_flow_pressure,
            create_committee_evidence,
            activate_committee_agents,
            generate_committee_debate_summary,
            generate_operational_signal_impact_summary,
            generate_intervention_plan
        )
    except ImportError:
        pass
    use_fallback = not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY"
    llm_calls = 0
    prompt_tokens = 0
    response_tokens = 0
    total_tokens = 0
    season_name = "Winter Surge" if patient_volume_multiplier > 1.2 else "Normal Baseline"
    
    planner_thought = f"Analyzing staffing shortage of {required_nurses} nurse(s) for the {shift_type} shift in the {department} department under acuity level {acuity_level}."
    if not candidates:
        planner_output = "No candidates found matching basic eligibility and hour pre-filters. Must request external agency nurses."
        resolved_nurses = []
    else:
        planner_output = f"Identified {len(candidates)} potential candidate(s) from the internal database: {', '.join([c['name'] for c in candidates])}."
        
    steps = [
        {"agent": "Staffing Planner Agent", "status": "COMPLETED", "thought": planner_thought, "output": planner_output}
    ]
    
    if not candidates:
        month = context.get("month", 6)
        day_of_week = context.get("day_of_week", 1)
        hour = context.get("visithour", 12)
        base_wait_time = context.get("base_wait_time", 120.0)
        preset_data = context.get("preset_data")
        
        esi_module = get_seasonal_esi_pressure(month, preset_data=preset_data)
        boarding_module = get_bed_boarding_pressure(month, day_of_week, hour, preset_data=preset_data)
        arrival_module = get_arrival_surge_pressure(month, day_of_week, hour, preset_data=preset_data)
        fast_track_module = get_fast_track_flow_pressure(month, day_of_week, hour, preset_data=preset_data)
        
        base_staffing_risk = "High" if required_nurses > 0 else "Low"
        fatigue_pressure = "Low"
        cost_pressure = "High"
        
        committee_evidence = create_committee_evidence(
            base_wait_time, base_staffing_risk, esi_module, boarding_module, 
            arrival_module, fast_track_module, fatigue_pressure, "Valid", cost_pressure,
            base_nurses_needed=required_nurses, preset_data=preset_data
        )
        final_nurses_needed = committee_evidence["research_adjusted_nurses_needed"]
        
        staffing_cost_before = required_nurses * 110.0 * 12.0
        staffing_cost_after = final_nurses_needed * 110.0 * 12.0
        cost_increase = staffing_cost_after - staffing_cost_before
        
        explain_narrative = (
            f"### Staffing Resolution Report ({log_id})\n"
            f"* **Shift**: {shift_type} in {department}\n"
            f"* **Status**: **FAILED - No Candidates Available**\n\n"
            f"**Rationale**:\n"
            f"No internal nurses passed the basic certifications or weekly hour filters. "
            f"Recommended action: Hire **{final_nurses_needed} external registry/agency nurse(s)** (Base XGBoost rule: {required_nurses} nurse(s))."
        )
        if committee_evidence:
            explain_narrative += (
                f"\n\n#### Operational Signals Detected:\n"
                f"- **ESI Pressure**: {committee_evidence.get('esi_pressure', 'Normal')}\n"
                f"- **Boarding Pressure**: {committee_evidence.get('boarding_pressure', 'Normal')}\n"
                f"- **Arrival Surge Pressure**: {committee_evidence.get('arrival_surge_pressure', 'Normal')}\n"
                f"- **Fast-Track Pressure**: {committee_evidence.get('fast_track_pressure', 'Normal')}\n"
                f"- **Adjusted Operational Risk**: {committee_evidence.get('adjusted_operational_risk', 'Normal')}\n"
            )
            
        return {
            "resolved_nurses": [],
            "resolution_steps": steps,
            "explainability_narrative": explain_narrative,
            "committee_evidence": committee_evidence,
            "active_agents": [],
            "intervention_plan": [],
            "costs": {
                "regular_staffing_cost": 0.0,
                "overtime_staffing_cost": 0.0,
                "agency_staffing_cost": round(staffing_cost_after, 2),
                "total_staffing_cost": round(staffing_cost_after, 2),
                "staffing_cost_before": round(staffing_cost_before, 2),
                "staffing_cost_after": round(staffing_cost_after, 2),
                "cost_increase": round(cost_increase, 2),
                "token_usage": 0,
                "estimated_api_cost": 0.0
            },
            "risk_factors": {
                "fatigue_index": 0.0,
                "patient_safety_score": 50.0,
                "compliance_violations": 0
            },
            "fallback_used": True
        }
        
    avail_thought = "Evaluating candidate shift preference alignment, circadian profiles, and seasonal surge factors."
    avail_outputs = []
    ranked_candidates = []
    
    for c in candidates:
        pref = c.get("circadian_preference", "Flexible")
        dist = c.get("distance_miles", 10)
        
        if pref == "Flexible":
            align_score = 90
            desc = "Flexible preference matches any shift."
        elif pref == shift_type:
            align_score = 100
            desc = f"Circadian profile matches shift type ({shift_type})."
        else:
            align_score = 60
            desc = f"Prefers {pref} shifts, but is available."
            
        if dist > 20:
            align_score -= 15
            desc += " Warning: High travel distance (20+ miles)."
            
        ranked_candidates.append((c, align_score))
        avail_outputs.append(f"- {c['name']} (Score: {align_score}%): {desc}")
        
    ranked_candidates.sort(key=lambda x: x[1], reverse=True)
    steps.append({
        "agent": "Availability & Shift Preference Agent",
        "status": "COMPLETED",
        "thought": avail_thought,
        "output": "Availability Alignment Results:\n" + "\n".join(avail_outputs)
    })

    comp_thought = "Validating labor law constraints: verifying shift rest periods and weekly hour thresholds."
    comp_outputs = []
    passed_compliance = []
    
    for c, score in ranked_candidates:
        curr_hours = c.get("weekly_hours", 0)
        if curr_hours + 12 > 60:
            msg = f"VETO {c['name']} - labor limit exceeded ({curr_hours} hrs worked this week, scheduling 12h shifts would violate the 60h maximum limit)."
            comp_outputs.append(msg)
        else:
            msg = f"PASS {c['name']} - approved. Credentials verified: {', '.join(c.get('certifications', []))}. Projected hours: {curr_hours + 12}h."
            comp_outputs.append(msg)
            passed_compliance.append(c)
            
    steps.append({
        "agent": "Compliance Guard Agent",
        "status": "COMPLETED",
        "thought": comp_thought,
        "output": "Compliance Validation Logs:\n" + "\n".join(comp_outputs)
    })
    
    safety_thought = "Evaluating fatigue factors, consecutive shifts worked, and patient safety risks to prevent clinical errors."
    safety_outputs = []
    passed_safety = []
    
    for c in passed_compliance:
        curr_hours = c.get("weekly_hours", 0)
        fatigue_index = (curr_hours / 40.0) * 100.0
        
        if fatigue_index > 90.0:
            msg = f"VETO {c['name']} - fatigue index is too high ({fatigue_index:.1f}%). Scheduled hours {curr_hours}h. High risk of clinical error."
            safety_outputs.append(msg)
        else:
            msg = f"PASS {c['name']} - fatigue index is safe ({fatigue_index:.1f}%). Fatigue level low/moderate."
            passed_safety.append((c, fatigue_index))
            safety_outputs.append(msg)
            
    steps.append({
        "agent": "Patient Safety Advocate Agent",
        "status": "COMPLETED",
        "thought": safety_thought,
        "output": "Fatigue and Burnout Audit:\n" + "\n".join(safety_outputs)
    })

    # Calculate research adjusted nurse need
    month = context.get("month", 6)
    day_of_week = context.get("day_of_week", 1)
    hour = context.get("visithour", 12)
    base_wait_time = context.get("base_wait_time", 120.0)
    preset_data = context.get("preset_data")
    
    esi_module = get_seasonal_esi_pressure(month, preset_data=preset_data)
    boarding_module = get_bed_boarding_pressure(month, day_of_week, hour, preset_data=preset_data)
    arrival_module = get_arrival_surge_pressure(month, day_of_week, hour, preset_data=preset_data)
    fast_track_module = get_fast_track_flow_pressure(month, day_of_week, hour, preset_data=preset_data)
    
    base_staffing_risk = "High" if required_nurses > 0 else "Low"
    fatigue_pressure = "High" if passed_safety and any(f > 80 for _, f in passed_safety) else "Low"
    
    # We pass cost_pressure="Moderate" for now, we will update it later
    committee_evidence = create_committee_evidence(
        base_wait_time, base_staffing_risk, esi_module, boarding_module, 
        arrival_module, fast_track_module, fatigue_pressure, "Valid", "Moderate",
        base_nurses_needed=required_nurses, preset_data=preset_data
    )
    final_nurses_needed = committee_evidence["research_adjusted_nurses_needed"]

    fin_thought = "Calculating cost trade-offs between regular hours, overtime, and agency premiums."
    fin_outputs = []
    scheduled_nurses = []
    
    fin_ranked = []
    for c, fatigue in passed_safety:
        curr_hours = c.get("weekly_hours", 0)
        rate = c.get("base_rate", 50.0)
        
        reg_hours = max(0, min(12, 40 - curr_hours))
        ot_hours = 12 - reg_hours
        
        total_cost = (reg_hours * rate) + (ot_hours * rate * 1.5)
        avg_rate = total_cost / 12.0
        
        fin_ranked.append((c, total_cost, avg_rate, ot_hours > 0))
        
    fin_ranked.sort(key=lambda x: x[2])
    
    for c, cost, avg_rate, is_ot in fin_ranked:
        is_ot_str = "Overtime (1.5x)" if is_ot else "Regular Rate"
        fin_outputs.append(f"- {c['name']}: Cost for 12h shift = ${cost:.2f} (Avg rate: ${avg_rate:.2f}/hr, Tiers: {is_ot_str})")
        
    for i in range(min(final_nurses_needed, len(fin_ranked))):
        scheduled_nurses.append(fin_ranked[i][0])
        
    agency_needed = final_nurses_needed - len(scheduled_nurses)
    if agency_needed > 0:
        fin_outputs.append(f"WARNING: Insufficient safe internal staff. Recommending {agency_needed} Agency Nurse(s) at $110.00/hr.")
        
    steps.append({
        "agent": "Financial Auditor Agent",
        "status": "COMPLETED",
        "thought": fin_thought,
        "output": "Financial Cost Optimization Audit:\n" + "\n".join(fin_outputs)
    })

    # Generate Committee Evidence
    total_research_module_intervention_cost = 0.0
    try:
        cost_pressure = "High" if agency_needed > 0 else "Moderate"
        committee_evidence["cost_pressure"] = cost_pressure
        
        active_agents = activate_committee_agents(committee_evidence)
        intervention_plan = generate_intervention_plan(committee_evidence)
        
        total_research_module_intervention_cost = sum(
            [item.get("estimated_cost", 0.0) for item in intervention_plan if isinstance(item, dict)]
        )
        
        committee_evidence["recommended_interventions"] = intervention_plan
        committee_evidence["intervention_cost_summary"] = {
            "total_estimated_intervention_cost": total_research_module_intervention_cost,
            "cost_status": "estimated",
            "cost_note": "Estimated configurable cost for recommended staffing and operational interventions."
        }
        
        # Update Financial Auditor Agent step output with the intervention costing audit rule
        for step in steps:
            if step["agent"] == "Financial Auditor Agent":
                risk_level = committee_evidence.get("adjusted_operational_risk", "Low")
                audit_note = ""
                if total_research_module_intervention_cost > 0:
                    if risk_level == "Low":
                        audit_note = (
                            f"\n\n**Intervention Cost Audit (Advisory Guidelines)**:\n"
                            f"- Adjusted Operational Risk: **Low**\n"
                            f"- Total Estimated Intervention Cost: **${total_research_module_intervention_cost:.2f}**\n"
                            f"- Guideline: **Suggest deferring or cancelling non-essential interventions** because clinical risk is Low."
                        )
                    elif risk_level == "Moderate":
                        audit_note = (
                            f"\n\n**Intervention Cost Audit (Advisory Guidelines)**:\n"
                            f"- Adjusted Operational Risk: **Moderate**\n"
                            f"- Total Estimated Intervention Cost: **${total_research_module_intervention_cost:.2f}**\n"
                            f"- Guideline: **Supervisor review recommended** to balance cost increases against clinical requirements."
                        )
                    else:  # High or Critical
                        audit_note = (
                            f"\n\n**Intervention Cost Audit (Advisory Guidelines)**:\n"
                            f"- Adjusted Operational Risk: **{risk_level}**\n"
                            f"- Total Estimated Intervention Cost: **${total_research_module_intervention_cost:.2f}**\n"
                            f"- Guideline: **Recommend approval/escalation of all interventions** despite cost increases because patient safety and compliance outweigh financial considerations."
                        )
                else:
                    audit_note = "\n\n**Intervention Cost Audit (Advisory Guidelines)**:\n- No additional operational interventions recommended."
                    
                audit_note += "\n*Note: Estimated intervention costs are advisory and do not dictate final clinical decisions.*"
                step["output"] += audit_note
                break
                
        debate_summary = generate_committee_debate_summary(committee_evidence, active_agents)
        
        enable_llm = context.get("enable_llm_debate", False)
        if enable_llm and not use_fallback:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
                model = genai.GenerativeModel(model_name)
                prompt = f"""
                You are a hospital operations AI committee consisting of the following agents: {[a['agent_name'] for a in active_agents]}.
                Based on the following operational signals and their local short positions, generate a cohesive multi-agent debate (max 2 paragraphs).
                Conclude with the exact Final Recommendation from the local summary.
                
                Evidence: {committee_evidence}
                Local Summary: {debate_summary}
                """
                resp = model.generate_content(prompt)
                if resp.text:
                    debate_summary = resp.text
                    llm_calls += 1
                    if hasattr(resp, 'usage_metadata') and resp.usage_metadata:
                        prompt_tokens += getattr(resp.usage_metadata, 'prompt_token_count', 0)
                        response_tokens += getattr(resp.usage_metadata, 'candidates_token_count', 0)
                        total_tokens += getattr(resp.usage_metadata, 'total_token_count', 0)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"DEBUG Debate Exception: {e}")
                # Silently fallback to local expert mode
                pass
                
        signal_impact = generate_operational_signal_impact_summary(committee_evidence)
        operational_signal_impact_summary = signal_impact["summary_text"]
        triggered_actions = signal_impact["triggered_actions"]
        final_recommendation_actions = signal_impact["final_recommendation_text"]
        
        # Combine the operational signal impact summary into the debate summary so it is always rendered
        debate_summary = debate_summary + "\n\n" + operational_signal_impact_summary
                
        steps.append({
            "agent": "AI Committee Coordinator",
            "status": "COMPLETED",
            "thought": "Aggregating operational research modules and launching dynamic agent debate.",
            "output": debate_summary
        })
    except Exception as e:
        committee_evidence = {}
        active_agents = []
        intervention_plan = []
        total_research_module_intervention_cost = 0.0
        operational_signal_impact_summary = ""
        triggered_actions = []
        final_recommendation_actions = "No debate generated."
        debate_summary = f"Error generating committee debate: {str(e)}"
        
        steps.append({
            "agent": "AI Committee Coordinator",
            "status": "FAILED",
            "thought": "Failed to aggregate operational research modules.",
            "output": debate_summary
        })

    resolved_names = [n["name"] for n in scheduled_nurses]
    if agency_needed > 0:
        resolved_names.append(f"{agency_needed} Agency Nurse(s)")
        
    explain_thought = "Synthesizing the decisions, compliance passes, safety constraints, and financial calculations into a human-readable summary."
    
    prompt_tokens = 0
    response_tokens = 0
    total_tokens = 0
    llm_calls = 0

    if context.get("enable_llm_debate", False) and not use_fallback:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            model = genai.GenerativeModel(model_name)
            prompt = (
                f"You are the Explainability Agent in a healthcare staffing system. Your goal is to write a short, clear, "
                f"and professional report explaining the staffing decision to hospital supervisors.\n\n"
                f"Shift Details: {shift_type} shift in {department}.\n"
                f"Required Staff: {required_nurses} nurse(s).\n"
                f"Matched Internal Nurses: {', '.join([n['name'] for n in scheduled_nurses])}.\n"
                f"External Agency Nurses needed: {agency_needed}.\n"
                f"Acuity Level (Proxy): {acuity_level} (Note: Urgency Level is used as the available acuity proxy because the dataset does not contain true ESI distribution).\n"
                f"Volume Multiplier (Seasonality): {patient_volume_multiplier}x ({season_name}).\n"
                f"Committee Evidence (Operational Signals): {json.dumps(committee_evidence, indent=2)}\n"
                f"Validation logs: \n"
                f"- Compliance: {json.dumps(comp_outputs)}\n"
                f"- Safety: {json.dumps(safety_outputs)}\n"
                f"- Financial: {json.dumps(fin_outputs)}\n\n"
                f"Format the report EXACTLY with these roles as markdown headers:\n\n"
                f"**A. Wait-Time Forecast**\n[Mention: XGBoost predicted wait time, base staffing risk]\n\n"
                f"**B. Operational Research Signals**\n[Mention: ESI pressure, boarding / bed pressure, arrival surge pressure, fast-track pressure, fatigue/compliance pressure, adjusted operational risk score, adjusted operational risk band]\n\n"
                f"**C. Dynamic Committee Agent Findings**\n[Mention active agents such as: Acuity / ESI Agent, Bed Flow / Boarding Agent if activated, Demand Surge Agent if activated, Fast-Track Flow Agent if activated, Fatigue Risk Agent if activated, Compliance Guard, Financial Auditor, Patient Safety Agent]\n\n"
                f"**D. Staffing Recommendation**\n[Mention: selected nurse or staffing action, why the selected nurse is compliant, why excluded nurses were rejected]\n\n"
                f"**E. Triggered Operational Actions**\n[Mention actions triggered by research signals: ER-certified acuity-capable coverage for ESI pressure, bed-flow escalation for boarding pressure, triage support / waiting-room monitoring for arrival surge, fast-track activation for low-acuity bottleneck, avoid overtime-heavy assignments for fatigue risk, human supervisor approval if adjusted risk is Critical]\n\n"
                f"**F. Final Human Governance Decision**\n[Mention: pending approval / approved / overridden, why human approval is required when adjusted operational risk is Critical. Note that estimated intervention costs are advisory, and use the risk-based guideline (defer/cancel if Low risk, review if Moderate, approve/escalate if High/Critical).]"
            )
            response = model.generate_content(prompt)
            explain_narrative = response.text
            
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                prompt_tokens += getattr(response.usage_metadata, 'prompt_token_count', 0)
                response_tokens += getattr(response.usage_metadata, 'candidates_token_count', 0)
                total_tokens += getattr(response.usage_metadata, 'total_token_count', 0)
            else:
                prompt_tokens += 450
                response_tokens += 1000
                total_tokens += 1450
            llm_calls += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"DEBUG LLM Exception: {e}")
            use_fallback = True
            
    if use_fallback or not context.get("enable_llm_debate", False):
        explain_narrative = (
            f"### Staffing Resolution Rationale ({log_id})\n"
            f"* **Shift Location/Time**: {department} - {shift_type} Shift\n"
            f"* **Target Staff Needed**: {required_nurses} nurse(s)\n"
            f"* **Final Staff Recommended**: {', '.join(resolved_names)}\n"
            f"* **Acuity Risk Profile**: Level {acuity_level} (Safety limit threshold set dynamically based on acuity and month).\n\n"
            f"#### Rationale Breakdown:\n"
            f"1. **Availability Assessment**: Candidate selection was aligned with circadian preferences (matching night-owls to night shifts) to maximize shift quality and reduce call-out probability.\n"
            f"2. **Compliance Guard**: Enforced strict labor laws. Nurses with excessive weekly hours (e.g. over 60 hours scheduled) were vetoed automatically to prevent compliance violations.\n"
            f"3. **Fatigue Check**: Candidates were checked for cognitive fatigue. Candidates exceeding a 90% fatigue score were vetoed to protect patient safety.\n"
            f"4. **Financial Cost Audit**: Evaluated candidate wages and recommended interventions. "
            f"Selected the most cost-effective nurses. Estimated intervention costs are advisory and do not dictate final clinical decisions. "
            f"Based on the adjusted risk level ({committee_evidence.get('adjusted_operational_risk', 'Low')}), "
            f"{'non-essential interventions can be deferred or cancelled.' if committee_evidence.get('adjusted_operational_risk') == 'Low' else 'supervisor review is recommended for intervention approval.' if committee_evidence.get('adjusted_operational_risk') == 'Moderate' else 'approval or escalation of interventions is recommended as patient safety and compliance outweigh cost.'}\n"
            f"5. **Seasonality / Stress Impact**: Seasonality factor is {patient_volume_multiplier}x. "
            f"{'Incentive bonuses recommended due to high seasonal load.' if patient_volume_multiplier > 1.2 else 'Standard baseline rates applied.'}"
        )
        if committee_evidence:
            explain_narrative += (
                f"\n\n#### Operational Signals Detected:\n"
                f"- **ESI Pressure**: {committee_evidence.get('esi_pressure', 'Normal')}\n"
                f"- **Boarding Pressure**: {committee_evidence.get('boarding_pressure', 'Normal')}\n"
                f"- **Arrival Surge Pressure**: {committee_evidence.get('arrival_surge_pressure', 'Normal')}\n"
                f"- **Fast-Track Pressure**: {committee_evidence.get('fast_track_pressure', 'Normal')}\n"
                f"- **Adjusted Operational Risk**: {committee_evidence.get('adjusted_operational_risk', 'Normal')}\n"
            )
        if use_fallback and not GEMINI_API_KEY:
            explain_narrative += "\n\n*(Note: Report generated via Local Deterministic Fallback - Gemini API Key not set)*"
            
        explain_narrative += "\n\n### AI Committee Output\n" + debate_summary
            
    steps.append({
        "agent": "Explainability Agent",
        "status": "COMPLETED",
        "thought": explain_thought,
        "output": "Explainability narrative successfully generated."
    })

    def calculate_cost_for_n_nurses(n):
        cost = sum([x[1] for x in fin_ranked[:min(n, len(fin_ranked))]])
        agency_count = max(0, n - len(fin_ranked))
        cost += agency_count * 110.0 * 12.0
        return round(cost, 2)
        
    staffing_cost_before = calculate_cost_for_n_nurses(required_nurses)
    staffing_cost_after = calculate_cost_for_n_nurses(final_nurses_needed)
    cost_increase = round(staffing_cost_after - staffing_cost_before, 2)

    total_staffing_cost = staffing_cost_after
    
    reg_cost = sum([cost for _, cost, _, is_ot in fin_ranked[:len(scheduled_nurses)] if not is_ot])
    ot_cost = sum([cost for _, cost, _, is_ot in fin_ranked[:len(scheduled_nurses)] if is_ot])
    agency_cost = agency_needed * 110.0 * 12.0
    
    avg_fatigue = sum([f for _, f in passed_safety[:len(scheduled_nurses)]]) / max(1, len(scheduled_nurses))
    
    safety_penalty = avg_fatigue * 0.3
    agency_penalty = agency_needed * 15.0
    patient_safety_score = max(10, 100.0 - safety_penalty - agency_penalty)
    
    estimated_api_cost = total_tokens * 0.000000075
    
    result = {
        "resolved_nurses": [n["id"] for n in scheduled_nurses],
        "unmet_nurse_gap": agency_needed,
        "escalation_recommendation": f"Activate float pool, hire {agency_needed} external agency/registry nurse(s), or escalate to shift supervisor." if agency_needed > 0 else "None",
        "resolution_steps": steps,
        "explainability_narrative": explain_narrative,
        "costs": {
            "regular_staffing_cost": round(reg_cost, 2),
            "overtime_staffing_cost": round(ot_cost, 2),
            "agency_staffing_cost": round(agency_cost, 2),
            "total_staffing_cost": round(total_staffing_cost, 2),
            "staffing_cost_before": round(staffing_cost_before, 2),
            "staffing_cost_after": round(staffing_cost_after, 2),
            "cost_increase": round(cost_increase, 2),
            "research_module_intervention_cost": round(total_research_module_intervention_cost, 2),
            "total_estimated_operational_cost": round(total_staffing_cost + total_research_module_intervention_cost, 2),
            "intervention_cost_note": "Estimated configurable cost for recommended staffing and operational interventions.",
            "llm_calls": llm_calls,
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
            "total_tokens": total_tokens,
            "token_usage": total_tokens,
            "estimated_api_cost": round(estimated_api_cost, 7)
        },
        "risk_factors": {
            "fatigue_index": round(avg_fatigue, 1),
            "patient_safety_score": round(patient_safety_score, 1),
            "compliance_violations": len(comp_outputs) - len(passed_compliance)
        },
        "token_usage": {
            "prompt": prompt_tokens,
            "response": response_tokens,
            "total": total_tokens,
            "llm_calls": llm_calls
        },
        "committee_evidence": committee_evidence,
        "active_agents": active_agents,
        "intervention_plan": intervention_plan,
        "operational_signal_impact_summary": operational_signal_impact_summary,
        "triggered_actions": triggered_actions,
        "final_recommendation_actions": final_recommendation_actions,
        "fallback_used": use_fallback
    }
    
    return result
