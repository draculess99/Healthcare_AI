import json
import os
from .research_modules import run_all_modules
from .memory import get_memory_state, find_similar_bedflow_events
from .rag import get_relevant_policy
from .discharge_checklist import build_discharge_checklist, checklist_action_items

def prepare_committee_context(patient_data, model_outputs):
    research_outputs = run_all_modules(patient_data, model_outputs)
    discharge_checklist = build_discharge_checklist(patient_data, model_outputs)
    
    scenario = {
        "primary_bottleneck": patient_data.get("primary_discharge_bottleneck", "None"),
        "readmission_risk_level": model_outputs.get("readmission_risk_level", "Low"),
        "delay_risk_level": model_outputs.get("delay_risk_level", "Low"),
        "discharge_destination": patient_data.get("discharge_destination", "Home"),
        "home_support_level": patient_data.get("home_support_level", "Good"),
        "bed_occupancy_percent": patient_data.get("current_bed_occupancy_percent", 80),
        "ed_boarding_count": patient_data.get("ed_boarding_count", 0)
    }
    
    similar_events = find_similar_bedflow_events({"scenario_signature": scenario})
    if similar_events:
        memory_insight = f"Found {len(similar_events)} similar prior cases. "
        actions = [ev.get("committee_recommendation", "") for ev in similar_events]
        memory_insight += f"Common prior recommendations included: {', '.join(set(actions))}."
    else:
        memory_insight = "No closely matching prior bed-flow memory event was found."
        
    safety = research_outputs["safety"]["patient_safety_level"]
    delay_risk = model_outputs["delay_risk_level"]
    
    base_context = f"""
Patient Context:
- Age: {patient_data.get('age')}
- Diagnosis: {patient_data.get('diagnosis_group')}
- Acuity: {patient_data.get('acuity_level')}
- Primary Bottleneck: {patient_data.get('primary_discharge_bottleneck')}
- ED Boarding Count: {patient_data.get('ed_boarding_count')}
- Bed Occupancy: {patient_data.get('current_bed_occupancy_percent')}%

Model Outputs:
- Delay Risk: {delay_risk}
- Readmission Risk: {model_outputs.get('readmission_risk_level')}

Safety Module Constraint: {safety} (If Critical, you MUST hold discharge for safety).

Discharge Readiness Checklist:
- Status: {discharge_checklist.get('readiness_status')}
- Complete: {discharge_checklist.get('completed_count')} of {discharge_checklist.get('total_count')} ({discharge_checklist.get('completion_percent')}%)
- Active blockers: {', '.join(discharge_checklist.get('blocker_names', [])) or 'None'}

Memory Insight: {memory_insight}
"""
    rag_query = f"{patient_data.get('primary_discharge_bottleneck', '')} {patient_data.get('diagnosis_group', '')}"
    retrieved_policy = get_relevant_policy(rag_query)
    if retrieved_policy:
        base_context += f"\nRetrieved Hospital Policy:\n{retrieved_policy}\n"
    else:
        base_context += "\nRetrieved Hospital Policy: No specific policy retrieved.\n"
        
    return {
        "base_context": base_context,
        "safety": safety,
        "delay_risk": delay_risk,
        "memory_insight": memory_insight,
        "research_outputs": research_outputs,
        "discharge_checklist": discharge_checklist,
        "retrieved_policy": retrieved_policy
    }

def call_llm(prompt, decision_system, model_name, is_json=False):
    if decision_system == "Groq":
        from groq import Groq
        raw_key = os.environ.get("GROQ_API_KEY", "")
        client = Groq(api_key=raw_key.strip() if raw_key else None)
        kwargs = {
            "model": model_name or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0
        }
        if is_json:
            kwargs["response_format"] = {"type": "json_object"}
        completion = client.chat.completions.create(**kwargs)
        return completion.choices[0].message.content, completion.usage.total_tokens
    elif decision_system == "Gemini LLM":
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        model = genai.GenerativeModel(model_name or "gemini-1.5-flash")
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.0, "response_mime_type": "application/json" if is_json else "text/plain"}
        )
        return response.text, response.usage_metadata.total_token_count
    return "", 0

def run_safety_agent(context, decision_system, model_name):
    prompt = f"""You are the Patient Safety Advocate.
Your sole focus is clinical safety and preventing readmissions. Review the following patient context and argue either for caution (holding discharge) or proceeding. Keep your argument under 4 sentences.
{context['base_context']}"""
    try:
        res, tok = call_llm(prompt, decision_system, model_name, is_json=False)
        return res, tok, None
    except Exception as e:
        return "", 0, str(e)

def run_ops_agent(context, decision_system, model_name):
    prompt = f"""You are the Operations & Flow Manager.
Your sole focus is hospital capacity and throughput. Review the following patient context and argue for expediting discharge or escalating bottlenecks to free up beds. Keep your argument under 4 sentences.
{context['base_context']}"""
    try:
        res, tok = call_llm(prompt, decision_system, model_name, is_json=False)
        return res, tok, None
    except Exception as e:
        return "", 0, str(e)

def run_director_agent(context, safety_arg, ops_arg, decision_system, model_name):
    prompt = f"""You are the Clinical Director (Arbitrator).
Review the Patient Context and the arguments from your two committee members. Synthesize the debate and make the final decision.

{context['base_context']}

---
Safety Advocate Argument:
{safety_arg}

Operations Manager Argument:
{ops_arg}
---
Return your recommendation as a JSON object with EXACTLY these three keys:
{{
  "final_recommendation": "Short string of the decision",
  "action_plan": ["list", "of", "actionable", "steps"],
  "audit_reasoning": "Brief explanation for audit log, referencing the debate"
}}
Do not include markdown blocks or any other text outside the JSON.
"""
    try:
        res_json, tok = call_llm(prompt, decision_system, model_name, is_json=True)
        return json.loads(res_json), tok, None
    except Exception as e:
        import traceback
        return {}, 0, f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"


def run_committee(patient_data, model_outputs, decision_system="Internal Expert System", model_name=None):
    research_outputs = run_all_modules(patient_data, model_outputs)
    discharge_checklist = build_discharge_checklist(patient_data, model_outputs)
    checklist_actions = checklist_action_items(discharge_checklist)
    
    # 1. Retrieve similar events for memory insight
    scenario = {
        "primary_bottleneck": patient_data.get("primary_discharge_bottleneck", "None"),
        "readmission_risk_level": model_outputs.get("readmission_risk_level", "Low"),
        "delay_risk_level": model_outputs.get("delay_risk_level", "Low"),
        "discharge_destination": patient_data.get("discharge_destination", "Home"),
        "home_support_level": patient_data.get("home_support_level", "Good"),
        "bed_occupancy_percent": patient_data.get("current_bed_occupancy_percent", 80),
        "ed_boarding_count": patient_data.get("ed_boarding_count", 0)
    }
    
    similar_events = find_similar_bedflow_events({"scenario_signature": scenario})
    if similar_events:
        memory_insight = f"Found {len(similar_events)} similar prior cases. "
        actions = [ev.get("committee_recommendation", "") for ev in similar_events]
        memory_insight += f"Common prior recommendations included: {', '.join(set(actions))}."
    else:
        memory_insight = "No closely matching prior bed-flow memory event was found."

    # 2. Formulate AI Committee Recommendation
    action_plan = []
    final_rec = "Proceed with routine discharge preparation"
    human_review = True # Always True
    
    safety = research_outputs["safety"]["patient_safety_level"]
    delay_risk = model_outputs["delay_risk_level"]
    
    readiness_status = discharge_checklist.get("readiness_status", "Unknown")
    active_blockers = discharge_checklist.get("blockers", [])

    if safety == "Critical" or readiness_status == "Not Clinically Ready":
        final_rec = "Hold discharge for safety"
        action_plan.append("MD review required due to clinical instability or incomplete clinical readiness checks.")
    elif readiness_status == "Escalate Now":
        final_rec = "Escalate discharge blockers now"
        action_plan.extend(checklist_actions or ["Escalate critical discharge blocker to the bed-flow lead."])
    elif readiness_status == "Blocked" and active_blockers:
        top_blocker = active_blockers[0]
        final_rec = f"{top_blocker['owner']} escalation required: {top_blocker['item']}"
        action_plan.extend(checklist_actions)
    elif safety == "High":
        final_rec = "Case manager review required"
        action_plan.append("Lock in post-discharge support before proceeding.")
        action_plan.extend(checklist_actions)
    else:
        if delay_risk in ["High", "Critical"]:
            # Check bottlenecks when the discharge checklist has no higher-priority blockers.
            if research_outputs["rehab"]["placement_pressure_level"] in ["High", "Critical"]:
                final_rec = "Rehab placement escalation required"
                action_plan.append("Escalate SNF/Rehab placement to case manager.")
            elif research_outputs["insurance"]["insurance_pressure_level"] in ["High", "Critical"]:
                final_rec = "Insurance authorization escalation required"
                action_plan.append("Urgent UM review for auth.")
            elif research_outputs["pharmacy"]["pharmacy_pressure_level"] in ["High", "Critical"]:
                final_rec = "Pharmacy escalation required"
                action_plan.append("Prioritize MedRec for this patient.")
            elif research_outputs["transport"]["transport_pressure_level"] in ["High", "Critical"]:
                final_rec = "Transport escalation required"
                action_plan.append("Confirm EMS/family ETA.")
            elif research_outputs["home_care"]["home_care_pressure_level"] in ["High", "Critical"]:
                final_rec = "Home-care setup required"
                action_plan.append("Expedite home health agency intake.")
            else:
                final_rec = "Escalate bottleneck"
                action_plan.append("General delay risk flagged, review case.")
        elif readiness_status == "Almost Ready":
            final_rec = "Almost ready - clear remaining checklist items"
            action_plan.extend(checklist_actions or ["Clear remaining medium-priority discharge tasks."])
        else:
            final_rec = "Expedite discharge workflow after human review."
            action_plan.append("All critical discharge readiness checks are complete or not required.")

    # Avoid duplicated action lines if checklist and module rules overlap.
    action_plan = list(dict.fromkeys(action_plan))

    # 3. Multi-Agent LLM Override Logic
    token_usage = 0
    llm_error = None
    debate_transcript = None

    if decision_system != "Internal Expert System":
        base_context = f"""
Patient Context:
- Age: {patient_data.get('age')}
- Diagnosis: {patient_data.get('diagnosis_group')}
- Acuity: {patient_data.get('acuity_level')}
- Primary Bottleneck: {patient_data.get('primary_discharge_bottleneck')}
- ED Boarding Count: {patient_data.get('ed_boarding_count')}
- Bed Occupancy: {patient_data.get('current_bed_occupancy_percent')}%

Model Outputs:
- Delay Risk: {delay_risk}
- Readmission Risk: {model_outputs.get('readmission_risk_level')}

Safety Module Constraint: {safety} (If Critical, you MUST hold discharge for safety).

Discharge Readiness Checklist:
- Status: {discharge_checklist.get('readiness_status')}
- Complete: {discharge_checklist.get('completed_count')} of {discharge_checklist.get('total_count')} ({discharge_checklist.get('completion_percent')}%)
- Active blockers: {', '.join(discharge_checklist.get('blocker_names', [])) or 'None'}

Memory Insight: {memory_insight}
"""
        
        safety_prompt = f"""You are the Patient Safety Advocate.
Your sole focus is clinical safety and preventing readmissions. Review the following patient context and argue either for caution (holding discharge) or proceeding. Keep your argument under 4 sentences.
{base_context}"""

        ops_prompt = f"""You are the Operations & Flow Manager.
Your sole focus is hospital capacity and throughput. Review the following patient context and argue for expediting discharge or escalating bottlenecks to free up beds. Keep your argument under 4 sentences.
{base_context}"""

        def call_llm(prompt, is_json=False):
            if decision_system == "Groq":
                from groq import Groq
                raw_key = os.environ.get("GROQ_API_KEY", "")
                client = Groq(api_key=raw_key.strip() if raw_key else None)
                kwargs = {
                    "model": model_name or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0
                }
                if is_json:
                    kwargs["response_format"] = {"type": "json_object"}
                completion = client.chat.completions.create(**kwargs)
                return completion.choices[0].message.content, completion.usage.total_tokens
            elif decision_system == "Gemini LLM":
                import google.generativeai as genai
                genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
                model = genai.GenerativeModel(model_name or "gemini-1.5-flash")
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.0, "response_mime_type": "application/json" if is_json else "text/plain"}
                )
                return response.text, response.usage_metadata.total_token_count
            return "", 0

        try:
            # 1. Gather Arguments
            safety_arg, s_tokens = call_llm(safety_prompt, is_json=False)
            ops_arg, o_tokens = call_llm(ops_prompt, is_json=False)
            
            # 2. Arbitrate
            director_prompt = f"""You are the Clinical Director (Arbitrator).
Review the Patient Context and the arguments from your two committee members. Synthesize the debate and make the final decision.

{base_context}

---
Safety Advocate Argument:
{safety_arg}

Operations Manager Argument:
{ops_arg}
---
Return your recommendation as a JSON object with EXACTLY these three keys:
{{
  "final_recommendation": "Short string of the decision",
  "action_plan": ["list", "of", "actionable", "steps"],
  "audit_reasoning": "Brief explanation for audit log, referencing the debate"
}}
Do not include markdown blocks or any other text outside the JSON.
"""
            director_json_str, d_tokens = call_llm(director_prompt, is_json=True)
            
            # Aggregate results
            token_usage = s_tokens + o_tokens + d_tokens
            debate_transcript = {
                "safety_advocate": safety_arg,
                "operations_manager": ops_arg
            }
            
            llm_result = json.loads(director_json_str)
            final_rec = llm_result.get("final_recommendation", final_rec)
            action_plan = llm_result.get("action_plan", action_plan)
            audit_reasoning = llm_result.get("audit_reasoning", f"LLM Arbitrated based on {safety} safety, {delay_risk} delay risk.")
        except Exception as e:
            # Fallback to expert system if LLM fails
            llm_error = str(e)
            audit_reasoning = f"Based on {safety} safety, {delay_risk} delay risk. (LLM Fallback due to error: {llm_error})"
    else:
        audit_reasoning = f"Based on {safety} safety, {delay_risk} delay risk."

    return {
        "final_recommendation": final_rec,
        "risk_summary": {
            "delay_risk": delay_risk,
            "readmission_risk": model_outputs["readmission_risk_level"],
            "safety_level": safety
        },
        "primary_bottleneck": patient_data.get("primary_discharge_bottleneck", "None"),
        "action_plan": action_plan,
        "bed_capacity_impact": research_outputs["bed_capacity"],
        "discharge_checklist": discharge_checklist,
        "human_review_required": human_review,
        "memory_insight": memory_insight,
        "audit_reasoning": audit_reasoning,
        "research_outputs": research_outputs,
        "token_usage": token_usage,
        "llm_error": llm_error,
        "debate_transcript": debate_transcript
    }
