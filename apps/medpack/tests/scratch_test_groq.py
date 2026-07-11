import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.agents.adk_agents import run_committee

telemetry = {
    "item_name": "IV Start Kit",
    "department": "Emergency Department",
    "selected_model": "openai/gpt-oss-120b"
}
prediction = {"predicted_24h_demand": 15.0}
shortage = {"usable_stock": 1, "true_shortage_gap": 14.0, "risk_level": "High"}
priority = {"recommended_action": "Pack Now"}
memory = {}

res = run_committee(telemetry, prediction, shortage, priority, memory, agent_mode="remote")
print("=== GROQ OUTPUT ===")
print(json.dumps(res, indent=2))
print("===================")
