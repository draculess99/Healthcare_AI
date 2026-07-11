import os
import json
import uuid
import datetime
import urllib.request
import urllib.error
from flask import Flask, jsonify, request
from database.database import JSONDatabase
from backend.model import predict_wait_time, train_model, CSV_PATH, MODEL_PATH, load_model_payload, clear_model_payload_cache
from typing import Dict, Any, List

app = Flask(__name__)
db = JSONDatabase()


def _safe_int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return default

def _estimate_tokens(text):
    return max(1, len(str(text or "")) // 4)

def _build_live_debate_prompt(context, rec_nurses, rejected_candidates):
    rejected_ids = []
    for r in rejected_candidates or []:
        if isinstance(r, dict):
            rejected_ids.append(r.get("id", str(r)))
        else:
            rejected_ids.append(str(r))
    return f"""
Hospital Scenario Context:
{json.dumps(context, indent=2, default=str)}

Recommended Nurses by Cost & Fatigue-Aware Optimizer: {rec_nurses}
Rejected Candidates (Failed Compliance): {rejected_ids}

Please act as the following agents and generate a debate.
Format your response using these exact headings:

PART 1: STAFFING VS COMPLIANCE
**Staffing Planner Agent**: [argument]
**Compliance Guard Agent**: [argument]

PART 2: SAFETY VS COST
**Patient Safety Agent**: [argument]
**Financial Auditor Agent**: [argument]

PART 3: FINAL ARBITER
**Final Arbiter Agent**: [decision]
"""

def _parse_live_debate_text(response_text):
    response_text = response_text or ""
    staffing_part = response_text
    safety_part = "Live API response did not include a separate safety/cost section."
    final_part = "Live API response did not include a separate final arbiter section."
    if "PART 2:" in response_text:
        parts = response_text.split("PART 2:", 1)
        staffing_part = parts[0].replace("PART 1: STAFFING VS COMPLIANCE", "").strip()
        if "PART 3:" in parts[1]:
            subparts = parts[1].split("PART 3:", 1)
            safety_part = subparts[0].replace("SAFETY VS COST", "").strip()
            final_part = subparts[1].replace("FINAL ARBITER", "").strip()
        else:
            safety_part = parts[1].strip()
    return staffing_part, safety_part, final_part

GEMINI_PREFERRED_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.5-flash",
]

GEMINI_RETIRED_MODEL_MAP = {
    "gemini-1.5-flash": "gemini-2.0-flash",
    "gemini-1.5-pro": "gemini-2.5-flash",
    "gemini-3.1-flash-lite": "gemini-2.0-flash-lite",
}

def _get_gemini_api_key():
    return (
        os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_GENAI_API_KEY")
    )

def _get_groq_api_key():
    return os.environ.get("GROQ_API_KEY")

def _normalize_gemini_model_name(model_name):
    model_name = (model_name or os.environ.get("GEMINI_MODEL") or "gemini-2.0-flash").strip()
    if model_name.startswith("models/"):
        model_name = model_name.split("/", 1)[1]
    return GEMINI_RETIRED_MODEL_MAP.get(model_name, model_name)

def _fetch_available_gemini_models(api_key):
    """Return generateContent-capable Gemini model IDs available to this API key."""
    if not api_key:
        return []
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = []
        for m in payload.get("models", []):
            methods = m.get("supportedGenerationMethods") or m.get("supportedActions") or []
            if "generateContent" not in methods:
                continue
            name = m.get("name", "").replace("models/", "")
            base = m.get("baseModelId", "")
            for candidate in (base, name):
                if candidate and candidate.startswith("gemini-") and candidate not in models:
                    models.append(candidate)
        return models
    except Exception:
        return []

def _choose_gemini_model(selected_model, available_models):
    selected = _normalize_gemini_model_name(selected_model)
    if available_models:
        if selected in available_models:
            return selected
        for preferred in GEMINI_PREFERRED_MODELS:
            if preferred in available_models:
                return preferred
        return available_models[0]
    return selected

def _extract_gemini_text(payload):
    try:
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "\n".join([str(p.get("text", "")) for p in parts if p.get("text")]).strip()
    except Exception:
        return ""

def _call_gemini_rest(api_key, model_name, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    body = {
        "systemInstruction": {
            "parts": [{"text": "You are a clinical multi-agent orchestration system for hospital staffing."}]
        },
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4}
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_payload = json.loads(e.read().decode("utf-8"))
            message = err_payload.get("error", {}).get("message", str(e))
        except Exception:
            message = str(e)
        raise RuntimeError(f"{model_name}: HTTP {e.code} - {message}")

def _call_groq_rest(api_key, model_name, prompt):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "SafeStaff-AI/1.0"
    }
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a clinical multi-agent orchestration system for hospital staffing."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_payload = json.loads(e.read().decode("utf-8"))
            message = err_payload.get("error", {}).get("message", str(e))
        except Exception:
            message = str(e)
        raise RuntimeError(f"{model_name}: HTTP {e.code} - {message}")

def _call_live_gemini_debate(context, rec_nurses, rejected_candidates, model_target=None):
    """Call Gemini and return a normalized debate/token payload.

This version avoids retired Gemini 1.5 model IDs, asks the backend what models
are available to the API key, and records the model that actually succeeded.
"""
    selected_model = model_target or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    normalized_selected = _normalize_gemini_model_name(selected_model)

    api_key = _get_gemini_api_key()
    if not api_key:
        return {
            "success": False,
            "status": "failed",
            "error": "GOOGLE_API_KEY, GEMINI_API_KEY, or GOOGLE_GENAI_API_KEY is not set in the backend service.",
            "llm_calls": 0,
            "prompt_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
            "estimated_api_cost": 0.0,
            "model_used": "",
            "selected_model": selected_model,
            "attempted_models": []
        }

    prompt = _build_live_debate_prompt(context, rec_nurses, rejected_candidates)
    available_models = _fetch_available_gemini_models(api_key)
    primary_model = _choose_gemini_model(normalized_selected, available_models)
    candidate_models = []
    for m in [primary_model] + GEMINI_PREFERRED_MODELS:
        m = _normalize_gemini_model_name(m)
        if available_models and m not in available_models:
            continue
        if m not in candidate_models:
            candidate_models.append(m)
    if not candidate_models:
        candidate_models = [primary_model]

    errors = []
    for model_name in candidate_models:
        try:
            payload = _call_gemini_rest(api_key, model_name, prompt)
            response_text = _extract_gemini_text(payload)
            usage = payload.get("usageMetadata", {}) or {}
            pt = _safe_int(usage.get("promptTokenCount", 0))
            rt = _safe_int(usage.get("candidatesTokenCount", 0))
            tt = _safe_int(usage.get("totalTokenCount", 0))
            if tt <= 0:
                pt = _estimate_tokens(prompt)
                rt = _estimate_tokens(response_text)
                tt = pt + rt
            staffing_part, safety_part, final_part = _parse_live_debate_text(response_text)
            return {
                "success": True,
                "status": "called",
                "staffing_vs_compliance": staffing_part,
                "safety_vs_cost": safety_part,
                "final_arbiter": final_part,
                "raw_response": response_text,
                "llm_calls": 1,
                "prompt_tokens": pt,
                "response_tokens": rt,
                "total_tokens": tt,
                "estimated_api_cost": (pt * 0.000000075) + (rt * 0.0000003),
                "model_used": model_name,
                "selected_model": selected_model,
                "normalized_selected_model": normalized_selected,
                "available_models": available_models[:20],
                "attempted_models": candidate_models,
                "error": ""
            }
        except Exception as e:
            errors.append(str(e))

    return {
        "success": False,
        "status": "failed",
        "error": "Live Gemini API failed for all available candidate models. Last error: " + (errors[-1] if errors else "unknown error"),
        "llm_calls": 0,
        "prompt_tokens": 0,
        "response_tokens": 0,
        "total_tokens": 0,
        "estimated_api_cost": 0.0,
        "model_used": candidate_models[-1] if candidate_models else normalized_selected,
        "selected_model": selected_model,
        "normalized_selected_model": normalized_selected,
        "available_models": available_models[:20],
        "attempted_models": candidate_models,
        "errors": errors[-5:]
    }

def _call_live_groq_debate(context, rec_nurses, rejected_candidates, model_target=None):
    if not model_target:
        model_target = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        
    api_key = _get_groq_api_key()
    if not api_key:
        return {
            "success": False,
            "status": "failed",
            "error": "GROQ_API_KEY is not set in the backend service.",
            "llm_calls": 0,
            "prompt_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
            "estimated_api_cost": 0.0,
            "model_used": "",
            "selected_model": model_target,
            "attempted_models": []
        }

    prompt = _build_live_debate_prompt(context, rec_nurses, rejected_candidates)
    
    try:
        payload = _call_groq_rest(api_key, model_target, prompt)
        response_text = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = payload.get("usage", {})
        pt = usage.get("prompt_tokens", 0)
        rt = usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", 0)
        
        staffing_part, safety_part, final_part = _parse_live_debate_text(response_text)
        return {
            "success": True,
            "status": "called",
            "staffing_vs_compliance": staffing_part,
            "safety_vs_cost": safety_part,
            "final_arbiter": final_part,
            "raw_response": response_text,
            "llm_calls": 1,
            "prompt_tokens": pt,
            "response_tokens": rt,
            "total_tokens": tt,
            "estimated_api_cost": 0.0,
            "model_used": model_target,
            "selected_model": model_target,
            "normalized_selected_model": model_target,
            "available_models": [model_target],
            "attempted_models": [model_target],
            "error": ""
        }
    except Exception as e:
        return {
            "success": False,
            "status": "failed",
            "error": f"Live Groq API failed: {str(e)}",
            "llm_calls": 0,
            "prompt_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
            "estimated_api_cost": 0.0,
            "model_used": model_target,
            "selected_model": model_target,
            "normalized_selected_model": model_target,
            "available_models": [model_target],
            "attempted_models": [model_target],
            "errors": [str(e)]
        }

@app.route("/api/gemini_models", methods=["GET"])
def gemini_models():
    api_key = _get_gemini_api_key()
    if not api_key:
        return jsonify({"success": False, "has_key": False, "models": [], "error": "Gemini API key missing on backend service."}), 200
    models = _fetch_available_gemini_models(api_key)
    return jsonify({
        "success": True,
        "has_key": True,
        "models": models,
        "preferred_models": GEMINI_PREFERRED_MODELS,
        "default_model": _choose_gemini_model(os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"), models)
    })

@app.route("/api/groq_status", methods=["GET"])
def groq_status():
    api_key = _get_groq_api_key()
    return jsonify({
        "success": True,
        "has_key": bool(api_key)
    })

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok", "service": "SafeStaff AI backend"})

@app.route("/api/nurses", methods=["GET"])
def get_nurses():
    """Return the nurse registry, auto-seeding demo data if Railway starts empty."""
    db.ensure_demo_data()
    nurses = db.get_nurses()
    if not nurses:
        # Last-resort repair for partial/empty Railway runtime database.
        db.reset_db()
        nurses = db.get_nurses()
    return jsonify(nurses)

@app.route("/api/nurses", methods=["POST"])
def add_nurse():
    try:
        nurse_data = request.json or {}
        required_fields = ["id", "name", "certifications", "weekly_hours", "base_rate", "circadian_preference", "distance_miles"]
        for field in required_fields:
            if field not in nurse_data:
                return jsonify({"success": False, "error": f"Missing field: {field}"}), 400
        
        if db.add_nurse(nurse_data):
            return jsonify({"success": True, "message": f"Nurse {nurse_data['name']} added successfully."})
        return jsonify({"success": False, "error": "Failed to write nurse to database."}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/schedule", methods=["GET"])
def get_schedule():
    """Return the shift schedule, auto-seeding demo data if Railway starts empty."""
    db.ensure_demo_data()
    schedule = db.get_schedule()
    if not schedule:
        # Last-resort repair for partial/empty Railway runtime database.
        db.reset_db()
        schedule = db.get_schedule()
    return jsonify(schedule)

@app.route("/api/predict_wait", methods=["POST"])
def predict_wait():
    try:
        data = request.json or {}
        facility_size_beds = int(data.get("facility_size_beds", 200))
        month = int(data.get("month", 6))
        day_of_week = int(data.get("day_of_week", 1))
        visithour = int(data.get("visithour", 12))
        urgency_level = int(data.get("urgency_level", 3))
        nurse_to_patient_ratio = float(data.get("nurse_to_patient_ratio", 0.2))
        specialist_availability = int(data.get("specialist_availability", 1))
        hospital_name = data.get("hospital_name", "Riverside Medical Center")
        region = data.get("region", "Urban")
        
        wait_time = predict_wait_time(
            facility_size_beds=facility_size_beds,
            month=month,
            day_of_week=day_of_week,
            visithour=visithour,
            urgency_level=urgency_level,
            nurse_to_patient_ratio=nurse_to_patient_ratio,
            specialist_availability=specialist_availability,
            hospital_name=hospital_name,
            region=region
        )
        
        from backend.research_modules import (
            get_seasonal_esi_pressure, get_bed_boarding_pressure,
            get_arrival_surge_pressure, get_fast_track_flow_pressure,
            create_committee_evidence
        )
        
        preset_data = data.get("preset_data")
        esi_module = get_seasonal_esi_pressure(month, preset_data=preset_data)
        boarding_module = get_bed_boarding_pressure(month, day_of_week, visithour, preset_data=preset_data)
        arrival_module = get_arrival_surge_pressure(month, day_of_week, visithour, preset_data=preset_data)
        fast_track_module = get_fast_track_flow_pressure(month, day_of_week, visithour, preset_data=preset_data)
        
        season_factor = 0.25 if month in [12, 1, 2] else (0.10 if month in [7, 8] else 0.0)
        safety_thresh = max(60, int(100 * (1 - season_factor)))
        
        base_n = 0
        diff = wait_time - safety_thresh
        if diff <= 0:
            base_n = 0
        elif diff <= 30:
            base_n = 1
        elif diff <= 60:
            base_n = 2
        else:
            base_n = 3
            
        evidence = create_committee_evidence(
            wait_time,
            "High" if base_n > 0 else "Low",
            esi_module,
            boarding_module,
            arrival_module,
            fast_track_module,
            nurse_fatigue_pressure="Low",
            nurse_compliance_status="Valid",
            cost_pressure="Low",
            base_nurses_needed=base_n,
            preset_data=preset_data
        )
        
        return jsonify({
            "success": True,
            "predicted_wait_time": wait_time,
            "safety_threshold": safety_thresh,
            "evidence": evidence
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/resolve_shortage", methods=["POST"])
def resolve_shortage():
    try:
        data = request.json or {}
        shift_id = data.get("shift_id")
        date = data.get("date", str(datetime.date.today()))
        shift_type = data.get("shift_type", "Night")
        department = data.get("department", "Emergency")
        acuity_level = int(data.get("acuity_level", 3))
        required_nurses = int(data.get("required_nurses", 1))
        patient_volume_multiplier = float(data.get("patient_volume_multiplier", 1.0))
        
        all_nurses = db.get_nurses()
        
        eligible_nurses = []
        for nurse in all_nurses:
            req_cert = "Emergency" if department == "Emergency" else "ICU"
            if req_cert in nurse.get("certifications", []):
                eligible_nurses.append(nurse)
                
        pre_filtered_candidates = []
        for nurse in eligible_nurses:
            if nurse.get("weekly_hours", 0) + 12 <= 60:
                pre_filtered_candidates.append(nurse)
        
        log_id = "LOG_" + str(uuid.uuid4())[:8].upper()
        
        from backend.agents.adk_agents import run_adk_workflow
        
        adk_result = run_adk_workflow(
            log_id=log_id,
            shift_type=shift_type,
            department=department,
            acuity_level=acuity_level,
            required_nurses=required_nurses,
            candidates=pre_filtered_candidates,
            patient_volume_multiplier=patient_volume_multiplier,
            context={
                "date": date,
                "shift_type": shift_type,
                "department": department,
                "month": int(data.get("month", 6)),
                "day_of_week": int(data.get("day_of_week", 1)),
                "visithour": int(data.get("visithour", 12)),
                "base_wait_time": float(data.get("base_wait_time", 120.0)),
                "enable_llm_debate": data.get("enable_llm_debate", False),
                "preset_data": data.get("preset_data")
            }
        )
        
        live_debate = None
        if data.get("enable_llm_debate", False):
            live_context = {
                "scenario": {
                    "date": date,
                    "shift_type": shift_type,
                    "department": department,
                    "acuity_level": acuity_level,
                    "required_nurses": required_nurses,
                    "patient_volume_multiplier": patient_volume_multiplier,
                    "base_wait_time": float(data.get("base_wait_time", 120.0)),
                    "preset_data": data.get("preset_data")
                },
                "committee_evidence": adk_result.get("committee_evidence", {}),
                "explainability_narrative": adk_result.get("explainability_narrative", "")
            }
            provider = data.get("provider", "gemini")
            if provider == "groq":
                live_debate = _call_live_groq_debate(
                    live_context,
                    adk_result.get("resolved_nurses", []),
                    adk_result.get("rejected_candidates", []),
                    data.get("groq_model") or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
                )
            else:
                live_debate = _call_live_gemini_debate(
                    live_context,
                    adk_result.get("resolved_nurses", []),
                    adk_result.get("rejected_candidates", []),
                    data.get("gemini_model") or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
                )
            if live_debate and live_debate.get("success"):
                adk_result.setdefault("costs", {})
                for k in ["llm_calls", "prompt_tokens", "response_tokens", "total_tokens", "estimated_api_cost"]:
                    adk_result["costs"][k] = live_debate.get(k, 0)
                adk_result["token_usage"] = {
                    "prompt": live_debate.get("prompt_tokens", 0),
                    "response": live_debate.get("response_tokens", 0),
                    "total": live_debate.get("total_tokens", 0),
                    "llm_calls": live_debate.get("llm_calls", 0)
                }

        log_entry = {
            "id": log_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "shift_id": shift_id,
            "date": date,
            "shift_type": shift_type,
            "department": department,
            "acuity_level": acuity_level,
            "required_nurses": required_nurses,
            "resolved_nurses": adk_result["resolved_nurses"],
            "resolution_steps": adk_result["resolution_steps"],
            "explainability_narrative": adk_result["explainability_narrative"],
            "committee_evidence": adk_result.get("committee_evidence", {}),
            "active_agents": adk_result.get("active_agents", []),
            "intervention_plan": adk_result.get("intervention_plan", []),
            "operational_signal_impact_summary": adk_result.get("operational_signal_impact_summary", ""),
            "triggered_actions": adk_result.get("triggered_actions", []),
            "final_recommendation_actions": adk_result.get("final_recommendation_actions", "No debate generated."),
            "token_usage": adk_result.get("token_usage", {"prompt": 0, "response": 0, "total": 0, "llm_calls": 0}),
            "costs": adk_result["costs"],
            "live_debate": live_debate or {},
            "live_debate_status": (live_debate or {}).get("status", "not_requested"),
            "live_debate_error": (live_debate or {}).get("error", ""),
            "risk_factors": adk_result["risk_factors"],
            "status": "Pending Approval",
            "fallback_used": adk_result.get("fallback_used", False),
            "unmet_nurse_gap": adk_result.get("unmet_nurse_gap", 0),
            "escalation_recommendation": adk_result.get("escalation_recommendation", "None")
        }
        db.add_log(log_entry)
        
        return jsonify({
            "success": True,
            "log": log_entry,
            "live_usage": {
                "llm_calls": (live_debate or {}).get("llm_calls", 0),
                "prompt_tokens": (live_debate or {}).get("prompt_tokens", 0),
                "response_tokens": (live_debate or {}).get("response_tokens", 0),
                "total_tokens": (live_debate or {}).get("total_tokens", 0),
                "estimated_api_cost": (live_debate or {}).get("estimated_api_cost", 0.0),
                "status": (live_debate or {}).get("status", "not_requested"),
                "error": (live_debate or {}).get("error", ""),
                "model_used": (live_debate or {}).get("model_used", ""),
                "selected_model": (live_debate or {}).get("selected_model", data.get("gemini_model", "gemini-2.0-flash"))
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/approve_resolution", methods=["POST"])
def approve_resolution():
    try:
        data = request.json or {}
        log_id = data.get("log_id")
        
        logs = db.get_logs()
        target_log = None
        for log in logs:
            if log["id"] == log_id:
                target_log = log
                break
                
        if not target_log:
            return jsonify({"success": False, "error": "Log not found"}), 404
            
        if target_log["status"] != "Pending Approval":
            return jsonify({"success": False, "error": "Log is already " + target_log["status"]}), 400
            
        override_nurses = data.get("override_nurses")
        debate_costs = data.get("debate_costs")
        assigned_nurses = override_nurses if override_nurses is not None else target_log["resolved_nurses"]
        
        db_data = db._read_raw()
        for l in db_data.get("logs", []):
            if l["id"] == log_id:
                if override_nurses is not None:
                    l["resolved_nurses"] = override_nurses
                    l["status"] = "Approved with Override"
                else:
                    l["status"] = "Approved"
                if debate_costs:
                    l["costs"]["llm_calls"] = l["costs"].get("llm_calls", 0) + debate_costs.get("llm_calls", 0)
                    l["costs"]["prompt_tokens"] = l["costs"].get("prompt_tokens", 0) + debate_costs.get("prompt_tokens", 0)
                    l["costs"]["response_tokens"] = l["costs"].get("response_tokens", 0) + debate_costs.get("response_tokens", 0)
                    l["costs"]["total_tokens"] = l["costs"].get("total_tokens", 0) + debate_costs.get("total_tokens", 0)
                    l["costs"]["estimated_api_cost"] = l["costs"].get("estimated_api_cost", 0.0) + debate_costs.get("estimated_api_cost", 0.0)
                break
        db._write_raw(db_data)
            
        for nurse_id in assigned_nurses:
            db.update_nurse_hours(nurse_id, 12)
            
        shift_id = target_log.get("shift_id")
        if not shift_id or shift_id == "NEW_SHIFT":
            shift_id = "SHIFT_" + str(uuid.uuid4())[:8].upper()
            
        existing_schedule = db.get_schedule()
        shift_exists = False
        for s in existing_schedule:
            if s["id"] == shift_id:
                shift_exists = True
                break
                
        if shift_exists:
            db.update_shift_status(shift_id, "Staffed", assigned_nurses)
        else:
            new_shift = {
                "id": shift_id,
                "date": target_log["date"],
                "shift_type": target_log["shift_type"],
                "department": target_log["department"],
                "assigned_nurses": assigned_nurses,
                "acuity_level": target_log["acuity_level"],
                "predicted_wait_time": 45.0,
                "status": "Staffed"
            }
            db.add_schedule_shift(new_shift)
            
        return jsonify({
            "success": True,
            "message": "Resolution approved and roster updated successfully.",
            "scheduled_shift_id": shift_id,
            "assigned_nurses": assigned_nurses
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/reject_resolution", methods=["POST"])
def reject_resolution():
    try:
        data = request.json or {}
        log_id = data.get("log_id")
        
        if db.update_log_status(log_id, "Rejected"):
            return jsonify({"success": True, "message": "Resolution rejected."})
        return jsonify({"success": False, "error": "Log not found."}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "research_modules": "loaded"
    })

@app.route("/research-modules/status", methods=["GET"])
def modules_status():
    status = {}
    from backend.research_modules import _get_db_path
    for f in ["data_sources.json", "esi_seasonal_patterns.csv", "bed_boarding_pressure.csv", "arrival_surge_pressure.csv", "fast_track_flow.csv"]:
        status[f] = os.path.exists(_get_db_path(f))
    return jsonify({"success": True, "files_exist": status})

@app.route("/api/logs", methods=["GET"])
def get_logs():
    return jsonify(db.get_logs())

@app.route("/api/audit_logs", methods=["GET"])
def get_audit_logs():
    return jsonify(db.get_audit_logs())

@app.route("/api/audit_logs", methods=["POST"])
def add_audit_log():
    try:
        entry = request.json or {}
        if db.add_audit_log(entry):
            return jsonify({"success": True, "message": "Audit log added successfully."})
        return jsonify({"success": False, "error": "Failed to add audit log."}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/reset", methods=["POST"])
def reset_db():
    if db.reset_db():
        return jsonify({"success": True, "message": "Database reset to default mock values."})
    return jsonify({"success": False, "error": "Failed to reset database."}), 500

@app.route("/api/generate_live_debate", methods=["POST"])
def generate_live_debate():
    try:
        data = request.json or {}
        context = data.get("context", {})
        rec_nurses = data.get("rec_nurses", [])
        rejected_candidates = data.get("rejected_candidates", [])
        provider = data.get("provider", "gemini")
        if provider == "groq":
            debate = _call_live_groq_debate(context, rec_nurses, rejected_candidates, data.get("model") or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"))
        else:
            debate = _call_live_gemini_debate(context, rec_nurses, rejected_candidates, data.get("model") or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))
        status_code = 200 if debate.get("success") else 500
        return jsonify({
            "success": bool(debate.get("success")),
            "debate": debate,
            "usage": {
                "llm_calls": debate.get("llm_calls", 0),
                "prompt_tokens": debate.get("prompt_tokens", 0),
                "response_tokens": debate.get("response_tokens", 0),
                "total_tokens": debate.get("total_tokens", 0),
                "estimated_api_cost": debate.get("estimated_api_cost", 0.0),
                "status": debate.get("status", "failed"),
                "error": debate.get("error", ""),
                "model_used": debate.get("model_used", model_target),
                "selected_model": debate.get("selected_model", model_target),
                "normalized_selected_model": debate.get("normalized_selected_model", ""),
                "attempted_models": debate.get("attempted_models", []),
                "available_models": debate.get("available_models", [])
            },
            "model_used": debate.get("model_used", model_target),
            "selected_model": debate.get("selected_model", model_target),
            "normalized_selected_model": debate.get("normalized_selected_model", ""),
            "attempted_models": debate.get("attempted_models", []),
            "available_models": debate.get("available_models", []),
            "error": debate.get("error", "")
        }), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/record_live_data", methods=["POST"])
def record_live_data():
    try:
        data = request.json or {}
        live_path = os.path.join("data", "live_collected_data.csv")
        # Ensure directory exists
        os.makedirs(os.path.dirname(live_path), exist_ok=True)
        # Append to CSV, creating header if needed
        import pandas as pd
        df = pd.DataFrame([data])
        if not os.path.exists(live_path):
            df.to_csv(live_path, index=False)
        else:
            df.to_csv(live_path, mode='a', header=False, index=False)
        return jsonify({"success": True, "message": "Live data recorded."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/train", methods=["POST"])
def trigger_train():
    try:
        mse, r2 = train_model(CSV_PATH, MODEL_PATH)
        clear_model_payload_cache()
        return jsonify({"success": True, "metrics": {"mse": mse, "r2": r2}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/retrain_and_reload", methods=["POST"])
def retrain_and_reload():
    try:
        # Retrain model (includes live data)
        mse, r2 = train_model(CSV_PATH, MODEL_PATH)
        clear_model_payload_cache()
        # Reload model into memory (global variable)
        global xgb_model
        import pickle
        payload = load_model_payload(MODEL_PATH)
        xgb_model = payload["model"]
        return jsonify({"success": True, "metrics": {"mse": mse, "r2": r2}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/reset_live_data", methods=["POST"])
def reset_live_data():
    try:
        live_path = os.path.join("data", "live_collected_data.csv")
        if os.path.exists(live_path):
            os.remove(live_path)
        # Retrain model (this clears live data since the file is gone)
        mse, r2 = train_model(CSV_PATH, MODEL_PATH)
        clear_model_payload_cache()
        global xgb_model
        import pickle
        payload = load_model_payload(MODEL_PATH)
        xgb_model = payload["model"]
        return jsonify({"success": True, "message": "Live data reset and model retrained on original dataset.", "metrics": {"mse": mse, "r2": r2}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/inflow-memory", methods=["GET"])
def get_inflow_memory():
    try:
        from backend.inflow_memory import load_inflow_memory
        return jsonify(load_inflow_memory())
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/inflow-forecast", methods=["POST"])
def generate_inflow_forecast():
    try:
        data = request.json or {}
        from backend.inflow_memory import forecast_next_15_min_inflow
        result = forecast_next_15_min_inflow(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/update-inflow-memory", methods=["POST"])
def update_inflow_memory():
    try:
        data = request.json or {}
        forecasted = int(data.get("forecasted_volume", 0))
        actual = int(data.get("actual_volume", 0))
        
        from backend.inflow_memory import load_inflow_memory, update_inflow_memory_after_actual
        prev_mem = load_inflow_memory()
        updated = update_inflow_memory_after_actual(forecasted, actual, prev_mem)
        return jsonify(updated)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/update_memory_on_save", methods=["POST"])
def update_memory_on_save():
    try:
        data = request.json or {}
        scenario_signature = data.get("scenario_signature", {})
        forecasted_volume = data.get("forecasted_volume", 0)
        staffing_recommendation = data.get("staffing_recommendation", {})
        
        from backend.inflow_memory import update_memory_on_schedule_save
        updated = update_memory_on_schedule_save(scenario_signature, forecasted_volume, staffing_recommendation)
        return jsonify({"success": True, "updated_memory": updated})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/inflow-history", methods=["GET"])
def get_inflow_history():
    try:
        from backend.inflow_memory import load_inflow_history
        return jsonify(load_inflow_history())
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/find_similar_history", methods=["POST"])
def find_similar_history():
    try:
        data = request.json or {}
        scenario_signature = data.get("scenario_signature", {})
        from backend.inflow_memory import find_similar_historical_events
        similar_events = find_similar_historical_events(scenario_signature)
        return jsonify({"success": True, "similar_events": similar_events})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

_EVALUATION_CACHE = {}

@app.route("/api/model-evaluation", methods=["GET"])
def model_evaluation():
    """Return feature importances, actual vs predicted, and residual data for dashboard graphs."""
    try:
        import pickle
        import numpy as np
        import pandas as pd
        from sklearn.model_selection import train_test_split
        from backend.model import add_derived_features, CSV_PATH, MODEL_PATH, get_risk_bands

        if not os.path.exists(MODEL_PATH):
            return jsonify({"success": False, "error": "Model not trained yet."}), 400

        mtime = os.path.getmtime(MODEL_PATH)
        if MODEL_PATH in _EVALUATION_CACHE and _EVALUATION_CACHE[MODEL_PATH]["mtime"] == mtime:
            return jsonify(_EVALUATION_CACHE[MODEL_PATH]["data"])

        payload = load_model_payload(MODEL_PATH)

        model_pipeline = payload["model"]
        features_list = payload["features"]
        te = payload.get("target_encoding", {})
        global_mean = te.get("global_mean", 45.0)
        hosp_mean = te.get("hosp_mean", {})
        hosp_hour_mean = te.get("hosp_hour_mean", {})
        reg_mean = te.get("reg_mean", {})
        reg_hour_mean = te.get("reg_hour_mean", {})

        df = pd.read_csv(CSV_PATH)
        df = add_derived_features(df)

        target = "wait_time"
        X = df.drop(columns=[target, "patient_satisfaction", "Time to Registration (min)", "Time to Triage (min)", "Time to Medical Professional (min)", "Total Wait Time (min)", "Patient Outcome"], errors="ignore")
        y = df[target]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Apply historical features
        def apply_historical(data):
            d = data.copy()
            d['hospital_historical_avg_wait'] = d['hospital_name'].map(hosp_mean).fillna(global_mean)
            d['hospital_hour_historical_avg_wait'] = d.apply(lambda row: hosp_hour_mean.get(f"{row['hospital_name']}|{row['visithour']}", global_mean), axis=1)
            d['region_historical_avg_wait'] = d['region'].map(reg_mean).fillna(global_mean)
            d['region_hour_historical_avg_wait'] = d.apply(lambda row: reg_hour_mean.get(f"{row['region']}|{row['visithour']}", global_mean), axis=1)
            return d

        X_test = apply_historical(X_test)
        for feature in features_list:
            if feature not in X_test.columns:
                X_test[feature] = 0
        X_test = X_test[features_list]

        y_pred = model_pipeline.predict(X_test)
        residuals = (y_test.values - y_pred).tolist()

        # Feature importances from XGBoost booster
        xgb_model = model_pipeline.named_steps['regressor']
        preprocessor = model_pipeline.named_steps['preprocessor']

        def get_readable_xgboost_feature_names(preprocessor, original_features, xgb_model):
            try:
                raw_names = preprocessor.get_feature_names_out()
            except Exception:
                raw_names = []
                try:
                    for name, trans, columns in preprocessor.transformers_:
                        if name == 'cat' and trans != 'drop':
                            cats = trans.categories_
                            for i, col in enumerate(columns):
                                for cat in cats[i]:
                                    raw_names.append(f"{col}_{cat}")
                        elif name == 'cyc' and trans != 'drop':
                            for col in columns:
                                raw_names.append(f"{col}_sin")
                                raw_names.append(f"{col}_cos")
                        elif name == 'num' and trans != 'drop':
                            for col in columns:
                                raw_names.append(col)
                        elif name == 'remainder' and trans == 'passthrough':
                            pass
                except Exception:
                    pass

            if not raw_names or len(raw_names) != len(xgb_model.feature_importances_):
                return [f"feature_{i}" for i in range(len(xgb_model.feature_importances_))], False

            readable_names = []
            for name in raw_names:
                name = str(name).replace("cat__", "").replace("cyc__", "").replace("num__", "").replace("remainder__", "")
                if name.startswith("hospital_name_"): name = "Hospital: " + name.replace("hospital_name_", "")
                elif name.startswith("region_"): name = "Region: " + name.replace("region_", "")
                elif name.startswith("season_"): name = "Season: " + name.replace("season_", "")
                elif name.startswith("shift_type_"): name = "Shift Type: " + name.replace("shift_type_", "")
                elif name.startswith("x0_"): name = "Hospital: " + name.replace("x0_", "")
                elif name.startswith("x1_"): name = "Region: " + name.replace("x1_", "")
                elif name.startswith("x2_"): name = "Season: " + name.replace("x2_", "")
                elif name.startswith("x3_"): name = "Shift Type: " + name.replace("x3_", "")
                elif name.startswith("size_tier_"): name = "Size Tier: " + name.replace("size_tier_", "")
                elif name.startswith("x4_"): name = "Size Tier: " + name.replace("x4_", "")
                else:
                    name = name.replace("_", " ").title()
                readable_names.append(name)
            return readable_names, True

        transformed_names, mapping_success = get_readable_xgboost_feature_names(preprocessor, features_list, xgb_model)

        importances = xgb_model.feature_importances_.tolist()
        feature_imp = sorted(
            [{"feature": str(name), "importance": imp} for name, imp in zip(transformed_names, importances)],
            key=lambda x: x["importance"], reverse=True
        )[:25]  # Top 25

        # Risk band confusion matrix
        actual_bands = get_risk_bands(y_test.values)
        pred_bands = get_risk_bands(y_pred)

        band_labels = ["Low", "Moderate", "High", "Critical"]
        confusion = {}
        for actual_b in band_labels:
            confusion[actual_b] = {}
            for pred_b in band_labels:
                confusion[actual_b][pred_b] = int(np.sum((actual_bands == actual_b) & (pred_bands == pred_b)))

        # Sample 300 points for scatter plot (performance)
        sample_size = min(300, len(y_test))
        indices = np.random.RandomState(42).choice(len(y_test), sample_size, replace=False)
        actual_sample = y_test.values[indices].tolist()
        pred_sample = y_pred[indices].tolist()

        result_data = {
            "success": True,
            "feature_importances": feature_imp,
            "feature_mapping_success": mapping_success,
            "actual_vs_predicted": {
                "actual": actual_sample,
                "predicted": pred_sample
            },
            "residuals": residuals,
            "risk_band_confusion": confusion,
            "sample_size": sample_size,
            "total_test_size": len(y_test)
        }
        
        _EVALUATION_CACHE[MODEL_PATH] = {"mtime": mtime, "data": result_data}
        return jsonify(result_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    import os
    if not os.path.exists(MODEL_PATH):
        train_model(CSV_PATH, MODEL_PATH)
    # Load model into memory using pickle since it's a serialized Pipeline dictionary
    import pickle
    payload = load_model_payload(MODEL_PATH)
    xgb_model = payload["model"]

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug, use_reloader=False)


