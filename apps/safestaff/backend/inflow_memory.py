import os
import json
import datetime

MEMORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "inflow_memory_state.json")
HISTORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "inflow_memory_history.json")

def load_inflow_memory() -> dict:
    if not os.path.exists(MEMORY_FILE_PATH):
        # Create safe defaults
        default_memory = {
            "rolling_inflow_avg": 0.0,
            "last_prediction_delta": 0,
            "trend_direction": "stable",
            "last_forecasted_volume": 0,
            "last_actual_volume": 0,
            "memory_update_interval_minutes": 10,
            "last_updated": datetime.datetime.now().isoformat(),
            "memory_reasoning": "Initialized default state."
        }
        save_inflow_memory(default_memory)
        return default_memory
    
    with open(MEMORY_FILE_PATH, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            default_memory = {
                "rolling_inflow_avg": 0.0,
                "last_prediction_delta": 0,
                "trend_direction": "stable",
                "last_forecasted_volume": 0,
                "last_actual_volume": 0,
                "memory_update_interval_minutes": 10,
                "last_updated": datetime.datetime.now().isoformat(),
                "memory_reasoning": "Reset state due to corrupted JSON."
            }
            save_inflow_memory(default_memory)
            return default_memory

def save_inflow_memory(memory: dict) -> None:
    os.makedirs(os.path.dirname(MEMORY_FILE_PATH), exist_ok=True)
    with open(MEMORY_FILE_PATH, "w") as f:
        json.dump(memory, f, indent=4)

def forecast_next_15_min_inflow(current_telemetry: dict) -> dict:
    memory = load_inflow_memory()
    
    rolling_avg = memory.get("rolling_inflow_avg", 0.0)
    last_delta = memory.get("last_prediction_delta", 0)
    trend = memory.get("trend_direction", "stable")
    
    # Baseline telemetry-only prediction
    waiting_room_count = current_telemetry.get("waiting_room_count", 0)
    inflow_multiplier = current_telemetry.get("patient_inflow_multiplier", 1.0)
    surge_multiplier = current_telemetry.get("arrival_surge_multiplier", 1.0)
    
    base_forecast = (waiting_room_count * 0.15 * inflow_multiplier) + (10 * surge_multiplier)
    
    # Adjust based on memory
    adjusted_forecast = base_forecast
    reasoning_parts = []
    
    if last_delta > 0:
        # We underpredicted last time (actual > forecast)
        adjusted_forecast += last_delta * 0.5
        reasoning_parts.append(f"Increased forecast to compensate for prior underprediction (delta: +{last_delta}).")
    elif last_delta < 0:
        # We overpredicted last time (actual < forecast)
        adjusted_forecast += last_delta * 0.5 # last_delta is negative, so this subtracts
        reasoning_parts.append(f"Reduced forecast to compensate for prior overprediction (delta: {last_delta}).")
        
    if trend == "increasing":
        adjusted_forecast *= 1.1
        reasoning_parts.append("Applied +10% multiplier due to increasing trend.")
    elif trend == "decreasing":
        adjusted_forecast *= 0.9
        reasoning_parts.append("Applied -10% multiplier due to decreasing trend.")
        
    final_forecast = max(0, int(round(adjusted_forecast)))
    
    # Calculate confidence (lower if delta is large)
    confidence = 0.9
    if abs(last_delta) > 5:
        confidence = max(0.5, 0.9 - (abs(last_delta) * 0.05))
        
    surge_alert = final_forecast > 20
    
    reasoning_str = " ".join(reasoning_parts)
    if not reasoning_str:
        reasoning_str = "Forecast matches baseline telemetry."
    
    return {
        "forecasted_volume": final_forecast,
        "reasoning": f"Baseline adjustment: {reasoning_str} Rolling average is {rolling_avg:.1f}.",
        "confidence_score": round(confidence, 2),
        "surge_alert": surge_alert,
        "memory_used": {
            "rolling_inflow_avg": rolling_avg,
            "last_prediction_delta": last_delta,
            "trend_direction": trend
        }
    }

def update_inflow_memory_after_actual(forecasted_volume: int, actual_volume: int, previous_memory: dict) -> dict:
    last_delta = actual_volume - forecasted_volume
    
    prev_avg = previous_memory.get("rolling_inflow_avg", 0.0)
    new_avg = (0.75 * prev_avg) + (0.25 * actual_volume)
    
    if actual_volume > prev_avg + 2:
        trend = "increasing"
    elif actual_volume < prev_avg - 2:
        trend = "decreasing"
    else:
        trend = "stable"
        
    updated_memory = {
        "rolling_inflow_avg": round(new_avg, 2),
        "last_prediction_delta": last_delta,
        "trend_direction": trend,
        "last_forecasted_volume": forecasted_volume,
        "last_actual_volume": actual_volume,
        "memory_update_interval_minutes": 10,
        "last_updated": datetime.datetime.now().isoformat(),
        "memory_reasoning": f"Updated state: delta was {last_delta}, trend is {trend}."
    }
    
    save_inflow_memory(updated_memory)
    
    history_event = {
        "timestamp": datetime.datetime.now().isoformat(),
        "event_type": "manual_actual_update",
        "scenario_signature": None,
        "forecasted_volume": forecasted_volume,
        "actual_or_observed_volume": actual_volume,
        "prediction_delta": last_delta,
        "previous_memory": previous_memory,
        "updated_memory": updated_memory,
        "staffing_recommendation": None,
        "memory_reasoning": f"Manual update: Delta was {last_delta}, trend updated to {trend}."
    }
    append_inflow_history(history_event)
    
    return updated_memory

def load_inflow_history() -> list:
    if not os.path.exists(HISTORY_FILE_PATH):
        return []
    with open(HISTORY_FILE_PATH, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_inflow_history(history: list) -> None:
    os.makedirs(os.path.dirname(HISTORY_FILE_PATH), exist_ok=True)
    with open(HISTORY_FILE_PATH, "w") as f:
        json.dump(history, f, indent=4)

def append_inflow_history(event: dict) -> None:
    history = load_inflow_history()
    history.append(event)
    save_inflow_history(history)

def update_memory_on_schedule_save(scenario_signature: dict, forecasted_volume: int, staffing_recommendation: dict) -> dict:
    previous_memory = load_inflow_memory()
    
    updated_memory = {
        "rolling_inflow_avg": previous_memory.get("rolling_inflow_avg", 0.0),
        "last_prediction_delta": previous_memory.get("last_prediction_delta", 0),
        "trend_direction": previous_memory.get("trend_direction", "stable"),
        "last_forecasted_volume": forecasted_volume,
        "last_actual_volume": previous_memory.get("last_actual_volume", 0),
        "memory_update_interval_minutes": 10,
        "last_updated": datetime.datetime.now().isoformat(),
        "memory_reasoning": "Memory state saved from schedule update workflow. Waiting for actuals."
    }
    
    save_inflow_memory(updated_memory)
    
    history_event = {
        "timestamp": datetime.datetime.now().isoformat(),
        "event_type": "schedule_update",
        "scenario_signature": scenario_signature,
        "forecasted_volume": forecasted_volume,
        "actual_or_observed_volume": None,
        "prediction_delta": previous_memory.get("last_prediction_delta", 0),
        "previous_memory": previous_memory,
        "updated_memory": updated_memory,
        "staffing_recommendation": staffing_recommendation,
        "memory_reasoning": "Schedule updated. Recorded scenario signature for future similarity matching."
    }
    append_inflow_history(history_event)
    
    return updated_memory

def find_similar_historical_events(scenario_signature: dict) -> list:
    history = load_inflow_history()
    if not history:
        return []
        
    scored_events = []
    for event in history:
        score = 0
        sig = event.get("scenario_signature", {})
        
        if sig.get("arrival_pressure") == scenario_signature.get("arrival_pressure"):
            score += 2
        if sig.get("boarding_pressure") == scenario_signature.get("boarding_pressure"):
            score += 2
        if sig.get("fatigue_pressure") == scenario_signature.get("fatigue_pressure"):
            score += 1
        if sig.get("acuity_pressure") == scenario_signature.get("acuity_pressure"):
            score += 1
            
        ed_occ_diff = abs(sig.get("ed_occupancy_percent", 0) - scenario_signature.get("ed_occupancy_percent", 0))
        if ed_occ_diff <= 5:
            score += 2
        elif ed_occ_diff <= 10:
            score += 1
            
        wr_diff = abs(sig.get("waiting_room_count", 0) - scenario_signature.get("waiting_room_count", 0))
        if wr_diff <= 5:
            score += 2
        elif wr_diff <= 10:
            score += 1
            
        scored_events.append({"score": score, "event": event})
        
    scored_events.sort(key=lambda x: x["score"], reverse=True)
    
    top_3 = [item["event"] for item in scored_events if item["score"] > 2][:3]
    return top_3

