import pytest
from backend.ui_helpers import (
    get_status_light_mapping,
    get_token_display_text,
    get_token_subtext,
    HELPER_ASSESS_RISK,
    HELPER_LAUNCH_SOLVER,
    HELPER_SUBMIT_DECISION
)

def test_status_light_mapping():
    assert get_status_light_mapping("Critical")["label"] == "CRITICAL"
    assert get_status_light_mapping("Critical")["color"] == "red"
    assert get_status_light_mapping("High")["label"] == "HIGH"
    assert get_status_light_mapping("High")["color"] == "orange"
    assert get_status_light_mapping("Elevated")["label"] == "ELEVATED"
    assert get_status_light_mapping("Elevated")["color"] == "yellow"
    assert get_status_light_mapping("Medium")["label"] == "ELEVATED"
    assert get_status_light_mapping("Normal")["label"] == "NORMAL"
    assert get_status_light_mapping("Normal")["color"] == "green"
    assert get_status_light_mapping("Low")["label"] == "NORMAL"
    
    # Defaults
    assert get_status_light_mapping(None)["label"] == "NORMAL"
    assert get_status_light_mapping("")["label"] == "NORMAL"
    assert get_status_light_mapping("UnknownRisk")["label"] == "UNKNOWN"

def test_token_display_text():
    # 0 external tokens returns safe wording
    assert get_token_display_text(0, False) == "Local / rule-based agent mode"
    assert get_token_display_text(0, True) == "Local / rule-based agent mode"
    
    # Positive external tokens
    assert get_token_display_text(150, True) == "150 external tokens used"
    
    # Subtext tests
    assert get_token_subtext(0, False) == "No paid external LLM tokens used in this run"
    assert get_token_subtext(150, True) == "Google Gemini API tokens tracked"

def test_helper_constants_exist():
    assert "XGBoost wait-time forecast" in HELPER_ASSESS_RISK
    assert "operational pressure" in HELPER_LAUNCH_SOLVER
    assert "human-reviewed decision" in HELPER_SUBMIT_DECISION or "audit log" in HELPER_SUBMIT_DECISION
