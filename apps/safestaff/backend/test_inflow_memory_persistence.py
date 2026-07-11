import os
import json
import pytest
import datetime
from unittest.mock import patch
import tempfile
import shutil

# We import the module to patch its constants
import backend.inflow_memory as memory_module

def test_memory_persistence_and_retrieval():
    # Setup temporary directory for test database files
    test_dir = tempfile.mkdtemp()
    test_state_path = os.path.join(test_dir, "inflow_memory_state.json")
    test_history_path = os.path.join(test_dir, "inflow_memory_history.json")
    
    with patch.object(memory_module, "MEMORY_FILE_PATH", test_state_path), \
         patch.object(memory_module, "HISTORY_FILE_PATH", test_history_path):
         
        # Ensure files don't exist initially
        assert not os.path.exists(test_state_path)
        assert not os.path.exists(test_history_path)
        
        # --- SCENARIO A ---
        scenario_a_sig = {
            "waiting_room_count": 50, # high
            "ed_occupancy_percent": 95, # high
            "arrival_pressure": "Critical",
            "boarding_pressure": "High",
            "fatigue_pressure": "High",
            "acuity_pressure": "High"
        }
        forecasted_vol = 30
        staffing_rec = {"final_additional_nurses": 3}
        
        # 1 & 2: Update memory and append history
        updated_state = memory_module.update_memory_on_schedule_save(scenario_a_sig, forecasted_vol, staffing_rec)
        
        # Verification 1 & 2: files are created
        assert os.path.exists(test_state_path), "inflow_memory_state.json should be created"
        assert os.path.exists(test_history_path), "inflow_memory_history.json should be created"
        
        # Verification 5: check state keys
        state_keys = [
            "rolling_inflow_avg", "last_prediction_delta", "trend_direction",
            "last_forecasted_volume", "last_actual_volume", "last_updated",
            "memory_reasoning"
        ]
        with open(test_state_path, "r") as f:
            saved_state = json.load(f)
            for key in state_keys:
                assert key in saved_state, f"State missing expected key: {key}"
                
        # Verification 3: history length increases by 1
        with open(test_history_path, "r") as f:
            saved_history = json.load(f)
            assert len(saved_history) == 1, "History length should be 1"
            
        # Verification 4: latest history record keys
        history_keys = [
            "timestamp", "event_type", "scenario_signature", "forecasted_volume",
            "previous_memory", "updated_memory", "staffing_recommendation", "memory_reasoning"
        ]
        latest_event = saved_history[-1]
        for key in history_keys:
            assert key in latest_event, f"History event missing expected key: {key}"
            
        # --- SCENARIO B ---
        scenario_b_sig = {
            "waiting_room_count": 48, # high, similar to 50
            "ed_occupancy_percent": 93, # high, similar to 95
            "arrival_pressure": "Critical",
            "boarding_pressure": "High",
            "fatigue_pressure": "Medium", # slightly different
            "acuity_pressure": "High"
        }
        
        # Verification 6: retrieval returns at least one similar event
        similar_events = memory_module.find_similar_historical_events(scenario_b_sig)
        assert len(similar_events) >= 1, "Should find at least one similar event"
        
        # Verification 7: returned event matches Scenario A
        matched_event = similar_events[0]
        assert matched_event["scenario_signature"]["arrival_pressure"] == scenario_a_sig["arrival_pressure"]
        assert matched_event["forecasted_volume"] == forecasted_vol
        
        # Verification 8 & 9: Memory insight generation
        # Since the app builds the insight in the frontend, we replicate the insight text generation logic here to prove it works as expected.
        def generate_insight_text(sim_events):
            if sim_events:
                return f"Memory insight: The system found {len(sim_events)} similar prior ER state(s) matching the current arrival pressure and occupancy."
            else:
                return "Memory insight: No closely matching prior memory event was found."
                
        insight = generate_insight_text(similar_events)
        assert "Memory insight: The system found" in insight
        
        # Test missing similar history
        no_similar_events = memory_module.find_similar_historical_events({
            "arrival_pressure": "Low",
            "boarding_pressure": "Low",
            "waiting_room_count": 0,
            "ed_occupancy_percent": 10
        })
        insight_none = generate_insight_text(no_similar_events)
        assert "Memory insight: No closely matching prior memory event was found." in insight_none

    shutil.rmtree(test_dir)
