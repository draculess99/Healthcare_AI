import os
import json
from backend.supply_memory import (
    load_supply_memory,
    update_supply_memory_after_actual,
    MEMORY_STATE_PATH,
    MEMORY_EVENTS_PATH
)

def test_supply_memory_updates():
    # Remove existing files if present to test initialization
    if os.path.exists(MEMORY_STATE_PATH):
        os.remove(MEMORY_STATE_PATH)
    if os.path.exists(MEMORY_EVENTS_PATH):
        os.remove(MEMORY_EVENTS_PATH)
        
    mem = load_supply_memory()
    assert mem["rolling_usage_avg"] == 0.0
    assert mem["trend_direction"] == "stable"
    
    # Trigger update
    updated_mem = update_supply_memory_after_actual(
        predicted_demand=10.0,
        actual_usage=15.0,
        item_name="Oxygen Mask",
        department="ICU"
    )
    
    assert updated_mem["last_predicted_demand"] == 10.0
    assert updated_mem["last_actual_usage"] == 15.0
    assert updated_mem["last_prediction_delta"] == 5.0
    
    # 0.75 * 0.0 + 0.25 * 15.0 = 3.75
    assert updated_mem["rolling_usage_avg"] == 3.75
    
    # 15.0 > 0.0 + 2 -> increasing
    assert updated_mem["trend_direction"] == "increasing"
    
    # Check event file exists and contains a line
    assert os.path.exists(MEMORY_EVENTS_PATH)
    with open(MEMORY_EVENTS_PATH, "r") as f:
        events = [json.loads(line) for line in f if line.strip()]
    assert len(events) >= 1
    assert events[0]["event_type"] == "memory_update"
