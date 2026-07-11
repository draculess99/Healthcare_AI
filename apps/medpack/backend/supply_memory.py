import os
import json
from datetime import datetime

MEMORY_STATE_PATH = "database/supply_memory_state.json"
MEMORY_EVENTS_PATH = "database/supply_memory_events.jsonl"

def get_default_memory():
    return {
        "forecast_horizon_hours": 24,
        "memory_update_interval_minutes": 5,
        "rolling_usage_avg": 0.0,
        "last_prediction_delta": 0.0,
        "trend_direction": "stable",
        "last_predicted_demand": 0.0,
        "last_actual_usage": 0.0,
        "last_updated": datetime.now().isoformat(),
        "memory_reasoning": "Initialized supply memory."
    }

def load_supply_memory():
    os.makedirs("database", exist_ok=True)
    if not os.path.exists(MEMORY_STATE_PATH):
        default_mem = get_default_memory()
        save_supply_memory(default_mem)
        return default_mem
    try:
        with open(MEMORY_STATE_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading memory state, resetting: {e}")
        default_mem = get_default_memory()
        save_supply_memory(default_mem)
        return default_mem

def save_supply_memory(memory):
    os.makedirs("database", exist_ok=True)
    with open(MEMORY_STATE_PATH, "w") as f:
        json.dump(memory, f, indent=2)

def append_memory_event(event):
    os.makedirs("database", exist_ok=True)
    with open(MEMORY_EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")

def update_supply_memory_after_actual(predicted_demand, actual_usage, item_name, department):
    memory_before = load_supply_memory()
    
    last_prediction_delta = actual_usage - predicted_demand
    old_avg = memory_before.get("rolling_usage_avg", 0.0)
    new_avg = 0.75 * old_avg + 0.25 * actual_usage
    
    # trend direction logic
    if actual_usage > old_avg + 2:
        trend = "increasing"
    elif actual_usage < old_avg - 2:
        trend = "decreasing"
    else:
        trend = "stable"
        
    reasoning = (
        f"Actual usage ({actual_usage:.1f}) compared to rolling average ({old_avg:.1f}) "
        f"indicates a '{trend}' trend. Prediction delta is {last_prediction_delta:.1f} units."
    )
    
    memory_after = {
        "forecast_horizon_hours": 24,
        "memory_update_interval_minutes": 5,
        "rolling_usage_avg": round(float(new_avg), 2),
        "last_prediction_delta": round(float(last_prediction_delta), 2),
        "trend_direction": trend,
        "last_predicted_demand": round(float(predicted_demand), 2),
        "last_actual_usage": round(float(actual_usage), 2),
        "last_updated": datetime.now().isoformat(),
        "memory_reasoning": reasoning
    }
    
    save_supply_memory(memory_after)
    
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": "memory_update",
        "item_name": item_name,
        "department": department,
        "predicted_demand": round(float(predicted_demand), 2),
        "actual_usage": round(float(actual_usage), 2),
        "last_prediction_delta": round(float(last_prediction_delta), 2),
        "memory_before": memory_before,
        "memory_after": memory_after
    }
    append_memory_event(event)
    
    return memory_after
