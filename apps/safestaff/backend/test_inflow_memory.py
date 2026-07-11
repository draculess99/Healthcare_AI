import os
import json
import pytest
from backend.inflow_memory import load_inflow_memory, save_inflow_memory, forecast_next_15_min_inflow, update_inflow_memory_after_actual, MEMORY_FILE_PATH

def setup_module(module):
    if os.path.exists(MEMORY_FILE_PATH):
        os.remove(MEMORY_FILE_PATH)

def teardown_module(module):
    if os.path.exists(MEMORY_FILE_PATH):
        os.remove(MEMORY_FILE_PATH)

def test_load_inflow_memory_defaults():
    if os.path.exists(MEMORY_FILE_PATH):
        os.remove(MEMORY_FILE_PATH)
    memory = load_inflow_memory()
    assert memory["rolling_inflow_avg"] == 0.0
    assert memory["last_prediction_delta"] == 0
    assert memory["trend_direction"] == "stable"
    assert "Initialized default state" in memory["memory_reasoning"]
    assert os.path.exists(MEMORY_FILE_PATH)

def test_forecast_response_structure():
    telemetry = {
        "waiting_room_count": 10,
        "patient_inflow_multiplier": 1.0,
        "arrival_surge_multiplier": 1.0
    }
    result = forecast_next_15_min_inflow(telemetry)
    assert "forecasted_volume" in result
    assert "reasoning" in result
    assert "confidence_score" in result
    assert "surge_alert" in result
    assert "memory_used" in result

def test_positive_delta_increases_forecast():
    # Setup memory
    memory = load_inflow_memory()
    memory["last_prediction_delta"] = 10 # Underpredicted last time
    memory["rolling_inflow_avg"] = 5.0
    memory["trend_direction"] = "stable"
    save_inflow_memory(memory)
    
    telemetry = {
        "waiting_room_count": 10,
        "patient_inflow_multiplier": 1.0,
        "arrival_surge_multiplier": 1.0
    }
    
    # Base forecast would be (10 * 0.15) + 10 = 11.5
    # Adjusted with +10 delta = 11.5 + (10 * 0.5) = 16.5
    
    result = forecast_next_15_min_inflow(telemetry)
    assert result["forecasted_volume"] > 11
    assert result["confidence_score"] < 0.9 # Lower confidence due to large delta
    assert "Increased forecast to compensate" in result["reasoning"]

def test_negative_delta_reduces_forecast():
    # Setup memory
    memory = load_inflow_memory()
    memory["last_prediction_delta"] = -10 # Overpredicted last time
    memory["rolling_inflow_avg"] = 5.0
    memory["trend_direction"] = "stable"
    save_inflow_memory(memory)
    
    telemetry = {
        "waiting_room_count": 10,
        "patient_inflow_multiplier": 1.0,
        "arrival_surge_multiplier": 1.0
    }
    
    # Base forecast would be (10 * 0.15) + 10 = 11.5
    # Adjusted with -10 delta = 11.5 + (-10 * 0.5) = 6.5
    
    result = forecast_next_15_min_inflow(telemetry)
    assert result["forecasted_volume"] < 11
    assert result["confidence_score"] < 0.9 # Lower confidence
    assert "Reduced forecast to compensate" in result["reasoning"]

def test_update_memory_writes_delta():
    previous_memory = {
        "rolling_inflow_avg": 10.0,
        "last_prediction_delta": 0,
        "trend_direction": "stable"
    }
    
    updated = update_inflow_memory_after_actual(15, 20, previous_memory) # Forecasted 15, Actual 20
    assert updated["last_prediction_delta"] == 5
    assert updated["last_forecasted_volume"] == 15
    assert updated["last_actual_volume"] == 20
    
    # Average = 0.75 * 10 + 0.25 * 20 = 7.5 + 5 = 12.5
    assert updated["rolling_inflow_avg"] == 12.5
    
    # Trend = 20 > (10 + 2) so increasing
    assert updated["trend_direction"] == "increasing"
    
    # Verify file was saved
    with open(MEMORY_FILE_PATH, "r") as f:
        saved = json.load(f)
        assert saved["last_prediction_delta"] == 5
