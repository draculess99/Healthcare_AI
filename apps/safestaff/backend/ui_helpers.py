def get_status_light_mapping(adjusted_risk: str) -> dict:
    """
    Maps an operational risk score to an ER status light display properties.
    Expected mapping:
      - Low / Normal -> Normal / green
      - Medium / Elevated -> Elevated / yellow
      - High -> High / orange
      - Critical -> Critical / red
    """
    if not adjusted_risk or not isinstance(adjusted_risk, str):
        return {"label": "NORMAL", "color": "green", "status": "Normal"}
        
    risk_upper = adjusted_risk.upper()
    if risk_upper in ["CRITICAL"]:
        return {"label": "CRITICAL", "color": "red", "status": "Critical"}
    elif risk_upper in ["HIGH"]:
        return {"label": "HIGH", "color": "orange", "status": "High"}
    elif risk_upper in ["MEDIUM", "ELEVATED"]:
        return {"label": "ELEVATED", "color": "yellow", "status": "Elevated"}
    elif risk_upper in ["LOW", "NORMAL"]:
        return {"label": "NORMAL", "color": "green", "status": "Normal"}
    else:
        return {"label": "UNKNOWN", "color": "gray", "status": "Unknown"}

def get_token_display_text(token_count: int, is_live_mode: bool = False) -> str:
    """
    Returns honest token display wording based on usage.
    Ensures 0 tokens show the safe fallback message without falsely claiming paid APIs.
    """
    if token_count == 0 or not is_live_mode:
        return "Local / rule-based agent mode"
    return f"{token_count} external tokens used"

def get_token_subtext(token_count: int, is_live_mode: bool = False) -> str:
    """
    Returns explanatory subtext for the token gauge/badge.
    """
    if token_count == 0 or not is_live_mode:
        return "No paid external API tokens used in this run"
    return "Groq / External API tokens tracked"

# Button helper text constants
HELPER_ASSESS_RISK = "Runs XGBoost wait-time forecast and operational risk assessment."
HELPER_LAUNCH_SOLVER = "Combines staffing risk, operational pressure, and roster constraints."
HELPER_SUBMIT_DECISION = "Saves human-reviewed decision to audit log."
