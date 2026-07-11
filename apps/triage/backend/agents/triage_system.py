import os
import sys
import json
from dotenv import load_dotenv
try:
    from google import genai
except ImportError:
    genai = None

try:
    from groq import Groq
except ImportError:
    Groq = None

# Load .env file from the root 'triage' directory
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(root_dir, '.env'))

# Ensure backend modules can be imported
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from backend.memory import add_message, get_messages
from backend.logger import log_transaction
from backend.forecaster import get_disease_probability
from backend.esi_engine import assess_esi_acuity, format_esi_markdown
from backend.agents.command_agents import evaluation_command_agents
from backend.rag_engine import retrieve_guidelines


MODEL_VITAL_KEYS = ["age", "sex", "cp", "trestbps", "chol", "fbs", "thalach"]


def get_model_vitals(vitals):
    """Filter the richer triage payload down to the ML model's expected features."""
    defaults = {
        "age": 50,
        "sex": 1,
        "cp": 4,
        "trestbps": 120,
        "chol": 200,
        "fbs": 0,
        "thalach": 150,
    }
    clean = {}
    for key in MODEL_VITAL_KEYS:
        clean[key] = vitals.get(key, defaults[key])
    return clean


def expert_system_decision(notes, vitals, model_name, dataset_name="UCI Cleveland Original"):
    model_vitals = get_model_vitals(vitals)
    prob = get_disease_probability(**model_vitals, model_name=model_name, dataset_name=dataset_name)
    esi = assess_esi_acuity(vitals, notes, prob)
    priority_score = esi["priority_score"]
    agent_outputs = evaluation_command_agents(esi, vitals, notes, prob, model_name)

    if esi["esi_level"] <= 2:
        decision = "Critical / High Risk"
    elif esi["esi_level"] == 3:
        decision = "Urgent"
    elif esi["esi_level"] == 4:
        decision = "Less Urgent"
    else:
        decision = "Non-Urgent"

    response = (
        "**Expert System Clinical Assessment:**\n\n"
        f"- Disease Probability ({model_name}): {prob:.1%}\n"
        f"- ESI-Style Priority Score: {priority_score:.1f}/10\n"
        f"- Risk Level: **{decision}**\n\n"
        f"{format_esi_markdown(esi)}\n\n"
        f"*Note: This decision was made using deterministic ESI-style triage rules plus the {model_name} probability, without LLM synthesis.*"
    )
    return response, 0, esi, prob, priority_score, agent_outputs


def run_multi_agent_pipeline(vitals, notes, model_name, prob, priority_score, esi, engine_type, llm_model_name, session_id):
    history = get_messages(session_id)
    historical_context = ""
    if history:
        historical_context = "\n\n--- HISTORICAL CONTEXT ---\nHere are the most recent patient evaluations you completed. Use this to ensure your new assessment is logically consistent with your past decisions.\n\n"
        recent_history = history[-4:] # Last two full interactions
        for msg in recent_history:
            role = "Previous Patient Data" if msg["role"] == "user" else "Your Past Decision"
            historical_context += f"[{role}]:\n{msg['content']}\n\n"

    esi_markdown = format_esi_markdown(esi)
    agent_outputs = evaluation_command_agents(esi, vitals, notes, prob, model_name)

    system_prompt = (
        "You are a medical AI decision support system. "
        "The deterministic ESI-style acuity engine is the safety source of truth. "
        "Do not downgrade below its recommended acuity. You may explain, summarize, and add cautious workflow suggestions, "
        "but final decisions must remain clinician-confirmed."
        + historical_context
    )
    # Retrieve RAG Guidelines
    rag_query = f"Patient presenting with {vitals.get('chief_complaint', 'unknown')}, pain {vitals.get('pain_score', 0)}/10, heart rate {vitals.get('thalach', 0)}."
    rag_context = retrieve_guidelines(rag_query)

    analyst_prompt = (
        f"Analyze the following patient data.\n"
        f"Vitals and triage inputs: {vitals}\n"
        f"Clinical Notes: '{notes}'\n"
        f"{model_name} predicts {prob:.1%} probability of heart disease.\n"
        f"Deterministic ESI-style engine output:\n{esi_markdown}\n\n"
        f"{rag_context}\n"
        "Draft a preliminary clinical assessment. State the ESI acuity, risk level, red flags, and next action. "
        "Explicitly cite the retrieved clinical guidelines if applicable. Do not recommend medication dosages."
    )

    total_tokens = 0

    def call_llm(prompt, role_system_prompt):
        nonlocal total_tokens

        # Dynamically reload the .env file right before calling the API
        # so we don't have to restart the server when keys change
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        load_dotenv(os.path.join(root_dir, '.env'), override=True)

        if engine_type == "Google LLM (Gemini)":
            if genai is None:
                raise ImportError("google-genai library is not installed. Run: pip install google-genai")
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
            response = client.models.generate_content(
                model=llm_model_name,
                contents=role_system_prompt + "\n\n" + prompt
            )
            text = response.text
            tokens = response.usage_metadata.total_token_count if hasattr(response, 'usage_metadata') and response.usage_metadata else len(prompt.split()) + len(text.split())
            total_tokens += tokens
            return text
        elif engine_type == "Groq":
            if Groq is None:
                raise ImportError("Groq library is not installed.")
            client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": role_system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model=llm_model_name,
            )
            text = chat_completion.choices[0].message.content
            tokens = chat_completion.usage.total_tokens if chat_completion.usage else len(prompt.split()) + len(text.split())
            total_tokens += tokens
            return text
        else:
            raise ValueError(f"Unknown engine: {engine_type}")

    try:
        # 1. Safety Sentinel deterministic agent checks protocol risk before LLM text generation.
        yield json.dumps({"step": "🛡️ Safety Sentinel Agent is reviewing red flags and downgrade risk..."}) + "\n"

        # 2. Analyst Drafts Assessment
        yield json.dumps({"step": "🔍 Analyst Agent is drafting preliminary assessment..."}) + "\n"
        analyst_draft = call_llm(analyst_prompt, system_prompt + " You are the Clinical Analyst. Draft a preliminary assessment.")

        # 2. Medical Reviewer Checks Draft
        yield json.dumps({"step": "⚕️ Medical Reviewer is cross-checking against ESI safety protocols..."}) + "\n"
        reviewer_prompt = (
            f"Review the Analyst's draft:\n\n{analyst_draft}\n\n"
            f"Safety-source ESI-style output:\n{esi_markdown}\n\n"
            f"{rag_context}\n"
            "Check against strict safety guardrails: ESI-1/ESI-2 cases must not be downgraded, severe BP/oxygen/respiratory/mental-status flags must be escalated, "
            "and no specific medication dosages should be recommended. Ensure the drafted assessment strictly adheres to the provided clinical guidelines. Provide a critique, correct errors, and explicitly approve the final logic."
        )
        reviewer_critique = call_llm(reviewer_prompt, system_prompt + " You are the Medical Reviewer. Ensure safety, strict protocol adherence, and apply guardrails.")

        # 3. Chief Editor Formats Report
        yield json.dumps({"step": "📝 Chief Editor is formatting final SOAP Note..."}) + "\n"
        editor_prompt = (
            f"Analyst Draft:\n{analyst_draft}\n\n"
            f"Reviewer Critique & Guardrails:\n{reviewer_critique}\n\n"
            f"Safety-source ESI-style output:\n{esi_markdown}\n\n"
            "Incorporate the critique and output a final, highly professional SOAP note (Subjective, Objective, Assessment, Plan). "
            "Put the ESI acuity and escalation requirement at the very top."
        )
        final_report = call_llm(editor_prompt, system_prompt + " You are the Chief Editor. Format the final output beautifully into a structured SOAP note.")

        yield json.dumps({"step": "📝 Documentation Agent is preparing SBAR handoff support..."}) + "\n"
        yield json.dumps({"done": True, "report": final_report, "tokens": total_tokens, "analyst_draft": analyst_draft, "reviewer_critique": reviewer_critique, "esi": esi, "agent_outputs": agent_outputs}) + "\n"
    except Exception as e:
        yield json.dumps({"error": f"LLM Error during multi-agent pipeline: {str(e)}", "tokens": total_tokens, "esi": esi}) + "\n"


def evaluate_patient(session_id, notes, engine_type, vitals, model_name, llm_model_name, dataset_name="UCI Cleveland Original"):
    model_vitals = get_model_vitals(vitals)
    prob = get_disease_probability(**model_vitals, model_name=model_name, dataset_name=dataset_name)
    esi = assess_esi_acuity(vitals, notes, prob)
    priority_score = esi["priority_score"]

    if engine_type == "Local Expert System (0 Tokens)":
        yield json.dumps({"step": "⚙️ Applying deterministic ESI-style triage rules..."}) + "\n"
        response_text, tokens, esi, prob, priority_score, agent_outputs = expert_system_decision(notes, vitals, model_name, dataset_name)
        yield json.dumps({"step": "🛡️ Safety Sentinel Agent is reviewing red flags and downgrade risk..."}) + "\n"
        yield json.dumps({"step": "📝 Documentation Agent is preparing SBAR handoff support..."}) + "\n"
        engine_used = "Expert System + ESI Acuity Engine + Command Agents"

        add_message(session_id, "user", f"Evaluated patient with vitals: {vitals}. ML Model: {model_name}. Engine: {engine_type} ({llm_model_name}). Notes: {notes}")
        add_message(session_id, "assistant", response_text)
        log_transaction("patient_evaluation", {
            "session_id": session_id,
            "engine": engine_used,
            "ml_model": model_name,
            "llm_model": llm_model_name,
            "tokens_used": tokens,
            "vitals": vitals,
            "notes": notes,
            "esi": esi,
            "agent_outputs": agent_outputs,
            "response": response_text
        })
        yield json.dumps({
            "done": True,
            "report": response_text,
            "tokens": tokens,
            "engine": engine_used,
            "ml_model": model_name,
            "llm_model": llm_model_name,
            "esi": esi,
            "disease_probability": prob,
            "priority_score": priority_score,
            "agent_outputs": agent_outputs,
        }) + "\n"
    else:
        engine_used = engine_type
        provider = "Groq" if engine_type == "Groq" else "Google LLM"

        for chunk in run_multi_agent_pipeline(vitals, notes, model_name, prob, priority_score, esi, engine_type, llm_model_name, session_id):
            data = json.loads(chunk)
            if "done" in data:
                raw_report = data["report"]
                total_tokens = data["tokens"]

                response_text = (
                    f"**Multi-Agent Committee Assessment ({provider} - {llm_model_name}):**\n\n"
                    f"- Disease Probability ({model_name}): {prob:.1%}\n"
                    f"- ESI-Style Priority Score: {priority_score:.1f}/10\n"
                    f"- Recommended Acuity: **{esi.get('esi_label')}**\n\n"
                    f"{format_esi_markdown(esi)}\n\n"
                    f"---\n\n{raw_report}"
                )

                add_message(session_id, "user", f"Evaluated patient with vitals: {vitals}. ML Model: {model_name}. Engine: {engine_type} ({llm_model_name}). Notes: {notes}")
                add_message(session_id, "assistant", response_text)

                log_transaction("patient_evaluation", {
                    "session_id": session_id,
                    "engine": engine_used,
                    "ml_model": model_name,
                    "llm_model": llm_model_name,
                    "tokens_used": total_tokens,
                    "vitals": vitals,
                    "notes": notes,
                    "esi": esi,
                    "agent_outputs": data.get("agent_outputs", evaluation_command_agents(esi, vitals, notes, prob, model_name)),
                    "response": response_text
                })

                yield json.dumps({
                    "done": True,
                    "report": response_text,
                    "tokens": total_tokens,
                    "engine": engine_used,
                    "ml_model": model_name,
                    "llm_model": llm_model_name,
                    "esi": esi,
                    "disease_probability": prob,
                    "priority_score": priority_score,
                    "analyst_draft": data.get("analyst_draft", ""),
                    "reviewer_critique": data.get("reviewer_critique", ""),
                    "agent_outputs": data.get("agent_outputs", evaluation_command_agents(esi, vitals, notes, prob, model_name))
                }) + "\n"
            else:
                yield chunk
